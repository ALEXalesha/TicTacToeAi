import os

import main


def test_selftest_plays_both_fields_and_writes_the_result(qapp, tmp_path, monkeypatch):
    out = tmp_path / "selftest.txt"
    home_before = os.environ["TICTACTOEAI_HOME"]
    assert main.main(["--selftest", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "ИТОГ: работает" in text
    assert "3x3: победитель" in text and "5x5: победитель" in text
    # статистику игрока не тронула: писала во временную папку, а не в нашу
    assert not os.path.exists(os.path.join(home_before, "stats.json"))
    monkeypatch.setenv("TICTACTOEAI_HOME", home_before)

