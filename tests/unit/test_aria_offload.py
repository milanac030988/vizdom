"""
AriaUiGrounder.available() gating, incl. the opt-in offload mode.

No model, no CUDA: torch.cuda is monkeypatched so the rules are checked on
any machine. The rules protect paid GPU hours, so they are pinned here.
"""

import types

import pytest

from visual_dom.evaluation.lifecycle.grounders import AriaUiGrounder


@pytest.fixture
def cuda(monkeypatch):
    """Pretend a CUDA card of the given size (GB, decimal) is present."""
    import torch

    def _set(total_gb):
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(torch.cuda, "get_device_properties",
                            lambda _i: types.SimpleNamespace(total_memory=total_gb * 1e9))
    return _set


def test_small_card_refused_without_offload(cuda, monkeypatch):
    monkeypatch.delenv("VIZDOM_ARIA_OFFLOAD", raising=False)
    cuda(51)                                   # a 48 GB card as torch reports it
    ok, why = AriaUiGrounder(quantize=False).available()
    assert not ok
    assert "VIZDOM_ARIA_OFFLOAD" in why         # tells the operator the way in


def test_big_card_accepted(cuda, monkeypatch):
    monkeypatch.delenv("VIZDOM_ARIA_OFFLOAD", raising=False)
    cuda(85)                                   # A100 80 GB / H100
    ok, _ = AriaUiGrounder(quantize=False).available()
    assert ok


def test_offload_accepts_48gb_and_says_so(cuda, monkeypatch):
    monkeypatch.setenv("VIZDOM_ARIA_OFFLOAD", "1")
    cuda(51)
    ok, why = AriaUiGrounder(quantize=False).available()
    assert ok and "OFFLOAD" in why


def test_offload_still_refuses_a_laptop_card(cuda, monkeypatch):
    monkeypatch.setenv("VIZDOM_ARIA_OFFLOAD", "1")
    cuda(24)                                   # spill would be ~26 GB: hopeless
    ok, why = AriaUiGrounder(quantize=False).available()
    assert not ok and "40" in why


def test_offload_env_zero_means_off(cuda, monkeypatch):
    monkeypatch.setenv("VIZDOM_ARIA_OFFLOAD", "0")
    cuda(51)
    ok, _ = AriaUiGrounder(quantize=False).available()
    assert not ok


def test_offload_budget_keeps_headroom(cuda, monkeypatch):
    cuda(51)                                   # 51e9 B = 47.5 GiB
    budget = AriaUiGrounder(quantize=False)._offload_budget()
    assert budget[0] == "42GiB"                # 47 - 5 GiB headroom
    assert budget["cpu"].endswith("GiB")
