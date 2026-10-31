// Runs inside the uptime-kuma container (cwd /app). Token arrives on stdin.
//   node kuma-ntfy.js wire   -> add/update the "ntfy → homelab" notification, link it to every
//                               monitor the SendGrid notification is linked to, make it the default
//   node kuma-ntfy.js test   -> send a test through Kuma's own ntfy provider with the stored config
const sqlite3 = require("@louislam/sqlite3");
const NAME = "ntfy → homelab";
const db = new sqlite3.Database("/app/data/kuma.db");
const q = (sql, p = []) => new Promise((ok, no) => db.all(sql, p, (e, r) => (e ? no(e) : ok(r))));
const run = (sql, p = []) => new Promise((ok, no) => db.run(sql, p, function (e) { e ? no(e) : ok(this); }));

async function wire(token) {
    const config = {
        name: NAME, type: "ntfy", isDefault: true, applyExisting: false,
        ntfyserverurl: "http://ntfy", ntfytopic: "homelab", ntfyPriority: 4,
        ntfyAuthenticationMethod: "accessToken", ntfyaccesstoken: token,
    };
    let [row] = await q("SELECT id FROM notification WHERE name = ?", [NAME]);
    await run("BEGIN");
    if (row) {
        await run("UPDATE notification SET config = ?, active = 1, is_default = 1 WHERE id = ?", [JSON.stringify(config), row.id]);
    } else {
        const user = (await q("SELECT id FROM user ORDER BY id LIMIT 1"))[0].id;
        row = { id: (await run("INSERT INTO notification (name, config, active, user_id, is_default) VALUES (?, ?, 1, ?, 1)",
            [NAME, JSON.stringify(config), user])).lastID };
    }
    await run("UPDATE notification SET is_default = 0 WHERE id != ?", [row.id]);
    const linked = await run(`INSERT INTO monitor_notification (monitor_id, notification_id)
        SELECT DISTINCT mn.monitor_id, ? FROM monitor_notification mn
        JOIN notification n ON n.id = mn.notification_id
        WHERE json_extract(n.config, '$.type') = 'smtp'
          AND mn.monitor_id NOT IN (SELECT monitor_id FROM monitor_notification WHERE notification_id = ?)`, [row.id, row.id]);
    await run("COMMIT");
    const [c] = await q("SELECT count(*) AS n FROM monitor_notification WHERE notification_id = ?", [row.id]);
    console.log(`notification id ${row.id}: linked ${linked.changes} new monitor(s), ${c.n} total; now the default for new monitors`);
}

async function test() {
    const [row] = await q("SELECT config FROM notification WHERE name = ?", [NAME]);
    if (!row) throw new Error("not wired yet");
    const Ntfy = require("./server/notification-providers/ntfy");
    const res = await new Ntfy().send(JSON.parse(row.config),
        `[homelab] Uptime Kuma alert test, ${new Date().toISOString()}. No action needed.`);
    console.log("test sent:", res);
}

let input = "";
process.stdin.on("data", (d) => (input += d)).on("end", async () => {
    try {
        if (process.argv[2] === "wire") await wire(input.trim());
        else await test();
    } catch (e) {
        console.error("FAILED:", e.message || e);
        process.exitCode = 1;
    } finally {
        db.close();
    }
});
