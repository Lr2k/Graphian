"""core ── Graphian の安定した契約(§5)。「Graphian とは何か」を定義する憲法。

同心円の幾何・遺伝子・接続点バッファ・セッション制御を含む。一度固めたら基本的に動かさない。
`environments` / `development` / `viz`(空き枠)はこの core の契約に依存する。
"""

from graphian.core.buffer import (
    ConnectionBuffer,
    ConnectionLayout,
    ConnectionPoint,
    Flow,
    InProcessConnectionBuffer,
    Snapshot,
)
from graphian.core.genome import (
    BodyGenome,
    Genome,
    NetworkGenome,
    crossover,
    genome_from_record,
)
from graphian.core.geometry import Geometry, NodePosition
from graphian.core.network import Network
from graphian.core.session import LineageRecord, PhylogeneticTree, Session, SessionConfig

__all__ = [
    # geometry
    "NodePosition",
    "Geometry",
    # genome
    "Genome",
    "NetworkGenome",
    "BodyGenome",
    "crossover",
    "genome_from_record",
    # buffer
    "Flow",
    "ConnectionPoint",
    "ConnectionLayout",
    "Snapshot",
    "ConnectionBuffer",
    "InProcessConnectionBuffer",
    # network
    "Network",
    # session
    "SessionConfig",
    "LineageRecord",
    "PhylogeneticTree",
    "Session",
]
