#!/usr/bin/env python3
"""
SSH Connection Manager for respecting MaxSessions limits.
Provides connection pooling and session management.
"""

import subprocess
import time
import os
from dotenv import load_dotenv
from contextlib import contextmanager

class SSHManager:
    def __init__(self):
        load_dotenv()
        self.ssh_user = os.getenv('SSH_USER')
        self.ssh_host = os.getenv('SSH_HOST')
        self._connection_delay = 2  # Seconds between connections
        self._last_connection_time = 0

    def _wait_for_connection_limit(self):
        """Ensure we don't exceed connection rate limits."""
        current_time = time.time()
        elapsed = current_time - self._last_connection_time
        if elapsed < self._connection_delay:
            time.sleep(self._connection_delay - elapsed)
        self._last_connection_time = time.time()

    def run_ssh_command(self, command, timeout=30):
        """Execute single SSH command with proper connection limiting."""
        self._wait_for_connection_limit()

        ssh_cmd = f"ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 {self.ssh_user}@{self.ssh_host} '{command}'"

        try:
            result = subprocess.run(
                ssh_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return result.returncode == 0, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "SSH command timed out"
        except Exception as e:
            return False, "", str(e)

    def run_multiple_commands(self, commands, timeout=60):
        """Execute multiple commands in a single SSH session."""
        self._wait_for_connection_limit()

        # Combine commands with proper error handling
        combined_command = " && ".join([f"({cmd})" for cmd in commands])

        ssh_cmd = f'''ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 {self.ssh_user}@{self.ssh_host} "
            {combined_command}
        "'''

        try:
            result = subprocess.run(
                ssh_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return result.returncode == 0, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "SSH commands timed out"
        except Exception as e:
            return False, "", str(e)

    @contextmanager
    def ssh_session(self, timeout=60):
        """Context manager for grouped SSH commands."""
        session_commands = []

        class SessionCommand:
            def __init__(self, manager):
                self.manager = manager
                self.commands = []

            def add_command(self, command):
                self.commands.append(command)

            def execute(self):
                if not self.commands:
                    return True, "", ""
                return self.manager.run_multiple_commands(self.commands, timeout)

        session = SessionCommand(self)
        try:
            yield session
        finally:
            # Execute all queued commands at once
            if session.commands:
                return session.execute()

# Singleton instance for easy importing
ssh_manager = SSHManager()