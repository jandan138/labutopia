from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.labutopia_fluid import run_formal_precontact_usd_dependency_preflight as runner


def test_mdl_import_parser_captures_local_and_absolute_module_references():
    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        module = Path(directory) / "material.mdl"
        module.write_text(
            """
            /* import ::ignored::*; */
            import ::base::*;
            using OmniPBR_ClearCoat import OmniPBR_ClearCoat;
            using .::aux_definitions import xy;
            export using ::scene import data_lookup_float;
            import ::nvidia::core_definitions::file_texture;
            """,
            encoding="utf-8",
        )

        imports = runner._mdl_import_modules(module)

    assert imports == (
        ".::aux_definitions",
        "::base",
        "::nvidia::core_definitions::file_texture",
        "::scene",
        "OmniPBR_ClearCoat",
    )
    assert (
        runner.MDL_LIBRARY_ROOT / "nvidia/core_definitions.mdl"
        in runner._mdl_module_candidates(
            "::nvidia::core_definitions::file_texture",
            owner=runner.MDL_BASE_ROOT / "OmniPBR.mdl",
        )
    )
    assert runner.MDL_LIBRARY_ROOT / "nvidia/aux_definitions.mdl" in runner._mdl_module_candidates(
        ".::aux_definitions",
        owner=runner.MDL_LIBRARY_ROOT / "nvidia/support_definitions.mdl",
    )
