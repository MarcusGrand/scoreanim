"""TEMPORARY shim (Phase R.1; deleted in R.3, ruling a): re-exports the
adapter package surface under the old module path by EXPLICIT name — a
star-import would skip the underscore names the tests and spikes use.
New code imports from scoreanim.core.engraving.verovio directly.
"""

from scoreanim.core.engraving.svg_geom import parse_transform  # noqa: F401
from scoreanim.core.engraving.verovio.attribution import (  # noqa: F401
    _attribute_ledger_dashes)
from scoreanim.core.engraving.verovio.decompose import (  # noqa: F401
    _PageDecomposer)
from scoreanim.core.engraving.verovio.identity import (  # noqa: F401
    _identity_for)
from scoreanim.core.engraving.verovio.kinds import (  # noqa: F401
    _CONTAINER_CLASSES, _KIND_BY_CLASS)
from scoreanim.core.engraving.verovio.mei_index import (  # noqa: F401
    _MeiIndex, _parse_mei)
from scoreanim.core.engraving.verovio.provider import (  # noqa: F401
    VerovioEngravingProvider)
from scoreanim.core.engraving.verovio.records import (  # noqa: F401
    AdapterNoteRecord, EngravedScore, _LoadState)
