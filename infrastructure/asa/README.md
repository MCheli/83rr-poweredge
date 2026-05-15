# ASA (Ark: Survival Ascended) Server

Self-hosted dedicated server, migrated from Nitrado in May 2026.

## How it runs

- **Image:** `mschnitzer/asa-linux-server:1.5.1` — wraps the Windows ASA dedicated server binary under GE-Proton on Linux
- **Entrypoint:** `/usr/bin/start_server` (Ruby/Bash script bundled in the image). Downloads SteamCMD on first run, pulls ASA app 2430930, fetches GE-Proton 10-17 via wget, launches `ArkAscendedServer.exe` under Proton
- **Port:** UDP 7777 forwarded WAN → `192.168.1.179` via UniFi
- **RCON:** TCP 11520 bound to `127.0.0.1` only (LAN admin)
- **DNS:** `ark.markcheli.com` → `173.48.98.211` (unproxied)
- **Volumes (named, Docker-managed):** `asa_server_files`, `asa_steam`, `asa_steamcmd`, `asa_cluster_shared`. Live in `/var/lib/docker/volumes/` on root partition. **Do NOT use bind mounts** — SteamCMD's 32-bit self-update fails when the host directory is owned by a UID not present in `/etc/passwd` inside the container (it can't `setuid` to a "real user" for sandboxed writes, so cache-dir creation returns `EACCES`)
- **Restart policy:** `unless-stopped`
- **Stop grace period:** 120 s (lets ASA save world cleanly on shutdown — default 10 s is too short)

## ASA save file format (what we learned)

### `.ark` files (the world)

ASA's world save is a **SQLite 3 database** (`file <save>.ark` → `SQLite format 3.`). Schema:

```sql
CREATE TABLE game (key BLOB primary key not null, value blob not null);
CREATE TABLE custom (key VARCHAR(64) primary key not null, value blob not null);
```

- **`game` table:** ~80k rows. Each row is one serialized actor (dino, structure, item, inventory) as Unreal Engine binary.
- **`custom` table:** small (~4 rows), holds save-level metadata:
  - `SaveHeader` — engine version, map registry, world streaming subdivision references (~300 KB)
  - `GameModeCustomBytes` — *can contain per-player profile records* (see below) (~200 KB on populated worlds)
  - `ActorTransforms` — bulk position cache (~2.7 MB)
  - `ActorTransformsDelta` — incremental position changes (tiny)

### `.arkprofile` files (per-player)

Each player has a `<EOS-account-id>.arkprofile` file in `ShooterGame/Saved/SavedArks/<MapName>/`. Contains UE-serialized `PrimalPlayerData` with:

- File header (32 B): save version + UE engine version + 16-byte internal UUID
- Class reference: `/Game/PrimalEarth/CoreBlueprints/PrimalPlayerDataBP.PrimalPlayerDataBP_C`
- Properties: `PlayerDataID` (UInt64, links to character actor in world), `UniqueID` (UniqueNetIdRepl carrying EOS ID), `SavedNetworkAddress`, `PlayerName` (Epic/Game Pass display name), `MyPlayerCharacterConfig` (appearance), `MyPersistentCharacterStats` (level, engrams, stat allocations), `TribeID`
- Trailer (21 B): `\x00\x01\x00\x00\x00` + 16-byte internal UUID

**Lookup at login:** server reads `<connecting-player-EOS>.arkprofile`, gets `PlayerDataID`, looks up the matching character actor in the `game` table, applies stats from the inline `MyPersistentCharacterStats`.

### `.arktribe` files (per-tribe)

Same UE serialization, contains `PrimalTribeData` with tribe name, owner PlayerDataID, member list, tribe log entries, dino count. Filename is `<tribe-id>.arktribe`. **Required on disk** — having tribe data only in the `game` table is not enough; ASA needs the `.arktribe` file present to fully load tribe membership at server startup.

### Other files

- `<player-id>.formertribeownerlog` — 62 bytes, records previous tribe owner when ownership transferred. Format: `<oldPlayerID>,<oldEOSID>,<timestamp>`
- `ServerPaintingsCache/` — player-uploaded paintings
- `TheIsland_WP_AntiCorruptionBackup.bak` — server-managed safety copy of `.ark`, written periodically
- `*.ark.gz` — historical snapshots (Nitrado naming convention)
- `*.arkrbf` — ARK ReBoot file, used for crash-recovery rollback

## Nitrado's embedded-profile quirk

**Critical:** Nitrado's hosted ASA stores `PrimalPlayerData` records **inside** the `GameModeCustomBytes` blob in the `.ark` SQLite database, instead of writing them as separate `<EOS>.arkprofile` files on disk. This means:

- **`ls` on Nitrado FTP shows NO `.arkprofile` files** even when characters exist and persist across restarts
- The fresh SteamCMD-installed ASA on this server **does** write separate files
- A naive `.ark` migration therefore brings the world but **loses the EOS→PlayerID binding** — every player spawns as a fresh level-1 character on first connect, even though their character body is still in the world

This is undocumented and not toggleable via any config flag we found. Either a Nitrado backend transformation, or a behavior of the older ASA build Nitrado runs.

## Migration recipe (Nitrado → self-host)

Mirror the world:
```bash
# Get FTP creds from Nitrado web panel (separate from account password)
wget -q --user=USER --password=PASS -r -np -nH --cut-dirs=2 \
  --reject="*.crashstack" \
  --exclude-directories="...Cache,...Crashes,...Logs" \
  "ftp://<nitrado-host>/<service-path>/Saved/"
```

Migrate the world:
```bash
docker compose stop asa
docker run --rm \
  -v /path/to/backup:/src:ro \
  -v 83rr-poweredge_asa_server_files:/v \
  alpine sh -c '
    cp /src/Saved/SavedArks/<Map>_WP/<Map>_WP.ark           /v/ShooterGame/Saved/SavedArks/<Map>_WP/
    cp /src/Saved/SavedArks/<Map>_WP/*_AntiCorruptionBackup.bak /v/ShooterGame/Saved/SavedArks/<Map>_WP/
    cp /src/Saved/Config/WindowsServer/*.ini                /v/ShooterGame/Saved/Config/WindowsServer/
    chown -R 25000:25000 /v/ShooterGame/Saved/
  '
docker compose up -d asa
```

Restore per-player profiles + tribe (extracted from the embedded `GameModeCustomBytes`):
```bash
# In a venv with arkparse installed (see "Tools" below)
python3 <<'PY'
from pathlib import Path
from arkparse.api.player_api import PlayerApi
from arkparse.saves.asa_save import AsaSave
from arkparse.player.ark_player import ArkPlayer
import arkparse.api.player_api as pa_mod
from arkparse.saves.save_connection import SaveConnection

# Patch ArkParse to load the LAST record in players_data
# (upstream skips it because the loop body is gated on next_player_data is not None)
def patched(self):
    pattern_none = bytes([0x4E, 0x6F, 0x6E, 0x65])
    positions = self.data.find_byte_sequence(self.PLAYER_DATA_NAME)
    end = len(self.data.byte_buffer)
    for i, pos in enumerate(positions):
        self.data.set_position(pos - 20)
        uuid_bytes = self.data.read_bytes(16)
        player_uuid = SaveConnection.byte_array_to_uuid(uuid_bytes)
        offset = pos - 36
        next_pd = positions[i + 1] if i + 1 < len(positions) else end
        last_none = self.data.find_last_byte_sequence_before(pattern_none, next_pd)
        if last_none is not None:
            self.player_data_pointers[player_uuid] = [uuid_bytes, offset, last_none + 4 - offset + 1]
pa_mod._TribeAndPlayerData._get_player_offsets = patched

save = AsaSave(Path("<your-mirrored>.ark"))
api = PlayerApi(save, no_pawns=True, bypass_inventory=True)

OUT = Path("/tmp/profiles"); OUT.mkdir(exist_ok=True)
for uuid_, data in api.data.players_data.items():
    pl = ArkPlayer(data, from_store=True)
    (OUT / f"{pl.unique_id}.arkprofile").write_bytes(api.data.get_ark_profile_raw_data(uuid_))

# Extract .arktribe for each active tribe
import arkparse.ark_tribe as at_mod
for tribe_uuid, tribe_data in api.data.tribes_data.items():
    t = at_mod.ArkTribe(tribe_data, from_store=True)
    if t.nr_of_dinos > 0:  # filter to active tribes
        (OUT / f"{t.tribe_id}.arktribe").write_bytes(api.data.get_ark_tribe_raw_data(tribe_uuid))
PY

# Then deploy
docker compose stop asa
docker run --rm -v /tmp/profiles:/in:ro -v 83rr-poweredge_asa_server_files:/v \
  alpine sh -c 'cp /in/*.arkprofile /in/*.arktribe /v/ShooterGame/Saved/SavedArks/<Map>_WP/ && chown 25000:25000 /v/ShooterGame/Saved/SavedArks/<Map>_WP/*'
docker compose up -d asa
```

## Operations

```bash
# Start / stop / restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d asa
docker compose stop asa     # graceful, honors 120s grace period
docker compose restart asa  # restart without recreating

# Logs
docker logs --tail 30 asa
docker exec asa bash -c 'tail -30 /home/gameserver/server-files/ShooterGame/Saved/Logs/ShooterGame.log'

# RCON (LAN-only on 127.0.0.1:11520)
docker exec asa asa-ctrl rcon --exec '<command>'
# Common commands: ListPlayers, GetChat, Broadcast "msg", DoExit

# In-game admin (with ServerAdminPassword)
# Open chat (Tab) and type:
EnableCheats <admin-password>
cheat ShowMyAdminManager     # GUI for player/tribe management
cheat ForceJoinTribe <id>    # join existing tribe
cheat setplayerlevel <N>     # set own level
cheat giveengrams            # unlock all engrams at level
cheat ForceTame              # claim/tame creature in front of you
```

## Tools

- **ArkParse** (`VincentHenauGithub/ark-save-parser`) — Python lib that reads `.ark`/`.arkprofile`/`.arktribe`. Has `PlayerApi.data.get_ark_profile_raw_data(uuid)` and `get_ark_tribe_raw_data(uuid)` which return ready-to-write file bytes. **Upstream bug:** skips the last record in `GameModeCustomBytes` (see patch in Migration recipe).
- **SQLite CLI / Python `sqlite3`** — inspect `.ark` directly (`SELECT key, length(value) FROM custom;` to map the embedded blobs).

## Configs

- `config/Game.ini` — game rules (multipliers, breeding, XP, etc.). Committed.
- `config/GameUserSettings.ini.template` — committed source of truth for server settings (PvP/PvE, taming rates, stack sizes, MaxPlayers, RCON port, etc.). Contains `__ADMIN_PASSWORD__` and `__SERVER_PASSWORD__` placeholders.
- `config/GameUserSettings.ini` — **NOT committed** (gitignored). Rendered automatically into the named volume on each container start by the `asa` service's entrypoint wrapper: `sed` substitutes `${ASA_SERVER_ADMIN_PASSWORD}` and `${ASA_SERVER_PASSWORD}` (from `.env`) into the template, writes to the volume's config path, chowns to UID 25000, then `exec`s `/usr/bin/start_server`.

To rotate passwords: change values in `.env`, then `docker compose up -d asa` (recreate). To change gameplay settings: edit the template, commit, recreate the container.

Required `.env` entries:
```bash
ASA_SERVER_ADMIN_PASSWORD=<admin-password-here>
ASA_SERVER_PASSWORD=<server-join-password-here>
```

## Backups

- World save lives in named volume `asa_server_files`. Volume backup with:
  ```bash
  docker run --rm -v 83rr-poweredge_asa_server_files:/v -v /mnt/nas/83rr-backup/asa:/dst alpine \
    tar czf /dst/asa-volume-$(date +%Y%m%d).tar.gz -C /v .
  ```
- One-time Nitrado mirror at `/mnt/nas/83rr-backup/asa/nitrado-mirror-2026-05-15.tar.gz` (full FTP snapshot from migration day, includes 19 timestamped `.ark.gz` historical save points).

## Known caveats

- **Ubuntu 22.04 elevated-idle CPU.** Upstream image documents elevated CPU at idle on Ubuntu 22.04. Observed here: ~22 % of one core when nobody is online. Acceptable on this 56-thread host but would matter on a smaller box.
- **Dinos may show "Claiming allowed" after a migration** despite correct tribe ownership. PvP-decay state propagates from the world data; ownership tag is still correct. Walk up and claim each one (or use `cheat ForceTame`).
- **Tribe log shows fewer entries in-game than the server actually has.** ASA limits the in-game tribe log display window; older entries are in the world but not shown.
- **The `Cheli7` Epic display name vs. `Human` in-game character name.** ASA's `PlayerName` field stores the platform/Epic gamer tag (`Cheli7`); the in-world character has a separate `PlayerCharacterName` set during character creation (`Human` here).
