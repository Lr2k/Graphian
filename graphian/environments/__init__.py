"""environments ── 環境・身体の空き枠(§1 / §7.1)。

環境(1D → 2D → 3D → 抽象空間)は core に触れずに python module として追加できる。本パッケージ
が初版で確定するのは `base.py` の抽象基底 `Environment`(契約)のみ。ダミー兼参照実装の
1 次元走光性(`phototaxis_1d.py`, §7.1)は本段階では未実装。
"""
