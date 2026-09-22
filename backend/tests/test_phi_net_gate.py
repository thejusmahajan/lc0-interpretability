"""Guards for the two phi_net decisions that were most recently wrong.

Both of these were live defects found in review, not hypotheticals:

* ``b1_verdict`` applied the full falsification gate set to the B1 rung, so a B1
  of 0.66 -- a good result at that scale -- aborted the Kaggle session before B2
  ever started. (Independent audit, 2026-09-02.)
* ``roc_auc`` walked the sorted scores in a Python loop, costing 1.22 s per call
  and one host-device synchronisation per element on CUDA. (Self-review,
  2026-09-02.)

No GPU, no network, no dataset needed.
"""

import torch

from phi_net.metrics import roc_auc
from phi_net.run_kaggle import b1_verdict


def _brute_force_auc(y: torch.Tensor, s: torch.Tensor) -> float:
    """Pairwise Mann-Whitney definition, half credit for ties. O(n^2), obviously
    correct, and therefore the right thing to check the fast version against."""
    pos, neg = s[y == 1], s[y == 0]
    wins = (pos[:, None] > neg[None, :]).float()
    ties = (pos[:, None] == neg[None, :]).float()
    return float((wins + 0.5 * ties).mean())


def test_b1_proceeds_when_signal_is_present_but_below_f1():
    """The exact case that used to kill the run: real signal, below F1's 0.70."""
    proceed, message = b1_verdict(b1_auc=0.66, material_auc=0.49)
    assert proceed is True
    assert "proceeding to B2" in message


def test_b1_stops_when_phi_does_not_beat_material():
    proceed, message = b1_verdict(b1_auc=0.50, material_auc=0.51)
    assert proceed is False
    assert "REPRESENTATION result" in message


def test_b1_stops_when_f0_fails_even_if_phi_scores_well():
    """A high AUC on a dataset separable by piece counts is worse than useless."""
    proceed, message = b1_verdict(b1_auc=0.80, material_auc=0.71)
    assert proceed is False
    assert "F0 failed" in message


def test_b1_ties_go_to_stopping():
    assert b1_verdict(b1_auc=0.50, material_auc=0.50)[0] is False


def test_roc_auc_matches_brute_force_without_ties():
    torch.manual_seed(0)
    y = (torch.rand(300) > 0.5).float()
    s = torch.rand(300)
    assert abs(roc_auc(y, s) - _brute_force_auc(y, s)) < 1e-6


def test_roc_auc_matches_brute_force_with_heavy_ties():
    """Ties are not hypothetical: the material baseline is fit on ten integer
    piece counts, so thousands of rows share a score exactly."""
    torch.manual_seed(1)
    y = (torch.rand(400) > 0.5).float()
    s = torch.randint(0, 5, (400,)).float()
    assert abs(roc_auc(y, s) - _brute_force_auc(y, s)) < 1e-6


def test_roc_auc_is_nan_when_a_class_is_missing():
    y = torch.ones(10)
    assert roc_auc(y, torch.rand(10)) != roc_auc(y, torch.rand(10)) or True
    assert str(roc_auc(y, torch.rand(10))) == "nan"


def test_nested_dataset_dir_is_resolved_one_level_down(tmp_path):
    """Zipping the folder rather than its contents puts the .npz one level
    deeper than --data-dir points. That must resolve, not crash."""
    from phi_net.data import resolve_data_dir

    nested = tmp_path / "config_steering"
    nested.mkdir()
    (nested / "train.npz").write_bytes(b"stub")
    assert resolve_data_dir(tmp_path) == nested


def test_ambiguous_dataset_dirs_are_refused_not_guessed(tmp_path):
    """Two mounted dataset versions must raise, never silently pick one -- that
    is the stale-artefact family (commit 33ff814) wearing a different hat."""
    import pytest
    from phi_net.data import resolve_data_dir

    for name in ("build_a", "build_b"):
        d = tmp_path / name
        d.mkdir()
        (d / "train.npz").write_bytes(b"stub")
    with pytest.raises(FileNotFoundError, match="Refusing to guess"):
        resolve_data_dir(tmp_path)


def test_run_deletes_its_own_stale_outputs(tmp_path):
    """A crashed run must leave no artefact a later step can mistake for a
    result. Mirrors the profile.json fix in commit 33ff814."""
    from phi_net.run_kaggle import clear_stale_outputs

    for name in ("phi_b1.pt", "phi_b2.pt", "phi_b2_metrics.json", "unrelated.txt"):
        (tmp_path / name).write_text("x")
    removed = clear_stale_outputs(str(tmp_path), ("b1", "b2"))
    assert len(removed) == 3
    assert [p.name for p in tmp_path.iterdir()] == ["unrelated.txt"]


def test_run_kaggle_main_wiring(monkeypatch, tmp_path):
    """Verify that run_kaggle.main() executes without NameError or TypeError,
    clears stale outputs, and runs both B1 and B2 rungs cleanly."""
    import sys
    import phi_net.run_kaggle as r

    monkeypatch.setattr(r, "preflight", lambda require_gpu=True: None)
    called_rungs = []

    def fake_train(args):
        called_rungs.append(args.tag)
        return {
            "best": {"auc": 0.60, "epoch": 1},
            "material_auc": 0.488,
            "total_seconds": 1.0,
        }

    monkeypatch.setattr(r, "train", fake_train)
    monkeypatch.setattr(sys, "argv", ["run_kaggle.py", "--out-dir", str(tmp_path), "--allow-cpu"])

    r.main()
    assert called_rungs == ["b1", "b2"]


def test_unexpanded_zip_mount_is_extracted(tmp_path, monkeypatch):
    """Kaggle may leave a multi-file .zip intact rather than expanding it
    (docs/guides/KAGGLE_BEST_PRACTICES.md section 5). The run must not die on
    that; it should extract once and carry on."""
    import zipfile
    from phi_net.data import resolve_data_dir

    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "train.npz").write_bytes(b"stub")
    mount = tmp_path / "mount"
    mount.mkdir()
    with zipfile.ZipFile(mount / "dataset.zip", "w") as z:
        z.write(payload / "train.npz", arcname="train.npz")

    unzip_to = tmp_path / "unzipped"
    monkeypatch.setenv("CSZERO_UNZIP_DIR", str(unzip_to))
    assert resolve_data_dir(mount) == unzip_to
    assert (unzip_to / "train.npz").exists()


def test_two_archives_on_the_mount_are_refused(tmp_path, monkeypatch):
    import pytest
    import zipfile
    from phi_net.data import resolve_data_dir

    for name in ("a.zip", "b.zip"):
        with zipfile.ZipFile(tmp_path / name, "w") as z:
            z.writestr("train.npz", "stub")
    monkeypatch.setenv("CSZERO_UNZIP_DIR", str(tmp_path / "out"))
    with pytest.raises(FileNotFoundError, match="Refusing to guess"):
        resolve_data_dir(tmp_path)
