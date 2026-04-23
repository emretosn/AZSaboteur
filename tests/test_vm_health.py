"""Tests for VM health utilities (connect command helpers)."""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

from saboteur.utils.vm_health import (
    check_port,
    ensure_nsg_rules,
    ensure_vm_running,
    get_vm_power_state,
    restart_xrdp,
)


class TestGetVmPowerState:
    @patch("saboteur.utils.vm_health._run_az")
    def test_returns_running(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="VM running\n", stderr=""
        )
        assert get_vm_power_state("rg-test", "vm-test") == "VM running"

    @patch("saboteur.utils.vm_health._run_az")
    def test_returns_deallocated(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="VM deallocated\n", stderr=""
        )
        assert get_vm_power_state("rg-test", "vm-test") == "VM deallocated"

    @patch("saboteur.utils.vm_health._run_az")
    def test_returns_none_on_failure(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        assert get_vm_power_state("rg-test", "vm-test") is None

    @patch("saboteur.utils.vm_health._run_az")
    def test_returns_none_on_empty(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert get_vm_power_state("rg-test", "vm-test") is None

    @patch("saboteur.utils.vm_health._run_az", side_effect=subprocess.TimeoutExpired(cmd="az", timeout=30))
    def test_returns_none_on_timeout(self, mock_az):
        assert get_vm_power_state("rg-test", "vm-test") is None


class TestEnsureVmRunning:
    @patch("saboteur.utils.vm_health.get_vm_power_state", return_value="VM running")
    def test_already_running(self, mock_state):
        assert ensure_vm_running("rg-test", "vm-test") is True

    @patch("saboteur.utils.vm_health._run_az")
    @patch("saboteur.utils.vm_health.get_vm_power_state")
    def test_starts_deallocated_vm(self, mock_state, mock_az):
        mock_state.side_effect = ["VM deallocated", "VM running"]
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert ensure_vm_running("rg-test", "vm-test") is True

    @patch("saboteur.utils.vm_health._run_az")
    @patch("saboteur.utils.vm_health.get_vm_power_state")
    def test_start_fails(self, mock_state, mock_az):
        mock_state.return_value = "VM deallocated"
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Start failed"
        )
        assert ensure_vm_running("rg-test", "vm-test") is False

    @patch("saboteur.utils.vm_health.get_vm_power_state", return_value=None)
    def test_unknown_state(self, mock_state):
        assert ensure_vm_running("rg-test", "vm-test") is False


class TestEnsureNsgRules:
    @patch("saboteur.utils.vm_health._run_az")
    def test_rules_already_exist(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="AllowRDP\nAllowSSH\n", stderr=""
        )
        assert ensure_nsg_rules("rg-test", "nsg-test") is True
        # Only called once (the list call), no create calls
        assert mock_az.call_count == 1

    @patch("saboteur.utils.vm_health._run_az")
    def test_creates_missing_rules(self, mock_az):
        # First call: list (no rules), then two create calls
        mock_az.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        assert ensure_nsg_rules("rg-test", "nsg-test") is True
        assert mock_az.call_count == 3

    @patch("saboteur.utils.vm_health._run_az")
    def test_creates_only_missing_rule(self, mock_az):
        # AllowRDP exists, AllowSSH missing
        mock_az.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="AllowRDP\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        assert ensure_nsg_rules("rg-test", "nsg-test") is True
        assert mock_az.call_count == 2
        # Verify the create call was for AllowSSH
        create_args = mock_az.call_args_list[1][0][0]
        assert "AllowSSH" in create_args

    @patch("saboteur.utils.vm_health._run_az")
    def test_list_failure(self, mock_az):
        mock_az.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        assert ensure_nsg_rules("rg-test", "nsg-test") is False

    @patch("saboteur.utils.vm_health._run_az")
    def test_create_failure(self, mock_az):
        mock_az.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Denied"),
        ]
        assert ensure_nsg_rules("rg-test", "nsg-test") is False


class TestCheckPort:
    @patch("saboteur.utils.vm_health.socket.create_connection")
    def test_port_open(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        assert check_port("10.0.0.1", 3389) is True

    @patch("saboteur.utils.vm_health.socket.create_connection", side_effect=ConnectionRefusedError)
    def test_port_refused(self, mock_conn):
        assert check_port("10.0.0.1", 3389) is False

    @patch("saboteur.utils.vm_health.socket.create_connection", side_effect=OSError("timeout"))
    def test_port_timeout(self, mock_conn):
        assert check_port("10.0.0.1", 3389) is False


class TestRestartXrdp:
    @patch("saboteur.utils.vm_health._run_vm_command", return_value="[stdout]\n\n[stderr]\n")
    def test_success(self, mock_cmd):
        assert restart_xrdp("rg-test", "vm-test") is True
        mock_cmd.assert_called_once_with("rg-test", "vm-test", "sudo systemctl restart xrdp")

    @patch("saboteur.utils.vm_health._run_vm_command", return_value=None)
    def test_failure(self, mock_cmd):
        assert restart_xrdp("rg-test", "vm-test") is False
