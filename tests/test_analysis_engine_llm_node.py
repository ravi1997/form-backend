from importlib import util
from pathlib import Path
from types import ModuleType
import sys
from unittest.mock import patch


def _load_analysis_engine_service():
    module_path = Path(__file__).resolve().parents[1] / "app/services/analysis_engine.py"
    fake_networkx = ModuleType("networkx")
    fake_networkx.DiGraph = object
    fake_networkx.is_directed_acyclic_graph = lambda graph: True
    fake_networkx.simple_cycles = lambda graph: []
    fake_networkx.is_weakly_connected = lambda graph: True
    fake_networkx.topological_sort = lambda graph: []
    fake_networkx.NetworkXError = RuntimeError
    sys.modules["networkx"] = fake_networkx

    fake_analysis = ModuleType("models.Analysis")

    class _Dummy:
        pass

    fake_analysis.Analysis = _Dummy
    fake_analysis.Node = _Dummy
    fake_analysis.Edge = _Dummy
    fake_analysis.Graph = _Dummy
    sys.modules["models.Analysis"] = fake_analysis

    fake_base = ModuleType("services.base")

    class _BaseService:
        def __init__(self, *args, **kwargs):
            self.db = type(
                "DB",
                (),
                {"analyses": None, "analysis_runs": None, "analysis_results": None},
            )()

    fake_base.BaseService = _BaseService
    sys.modules["services.base"] = fake_base
    module_name = "analysis_engine_test_module"
    spec = util.spec_from_file_location(module_name, module_path)
    module = util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.AnalysisEngineService


def test_llm_prompt_node_registers_and_formats_output():
    AnalysisEngineService = _load_analysis_engine_service()
    service = AnalysisEngineService()
    node_info = service.node_registry.get("llm_prompt")

    assert node_info is not None
    assert node_info["name"] == "LLM Prompt"

    node_data = {
        "title": "Summarize Intake",
        "input_ports": [{"id": "input", "input": "input"}],
        "properties": {
            "prompt_template": "Summarize the following data:\n{data}",
            "config": {"style": "bullet"},
        },
    }
    context = {
        "input": [
            {"patient_id": "P-1", "notes": "Stable"},
            {"patient_id": "P-2", "notes": "Needs follow up"},
        ]
    }

    with patch(
        "analysis_engine_test_module.LLMService.generate_text",
        return_value='{"summary":"ok","items":2}',
    ) as mock_generate_text:
        result = service._handle_llm_prompt(node_data, context)

    mock_generate_text.assert_called_once()
    assert result["type"] == "llm"
    assert result["input_rows"] == 2
    assert result["result"] == {"summary": "ok", "items": 2}
    assert "Summarize the following data" in result["prompt"]


def test_llm_prompt_node_requires_prompt_template():
    AnalysisEngineService = _load_analysis_engine_service()
    service = AnalysisEngineService()

    try:
        service._handle_llm_prompt(
            {"title": "Broken", "input_ports": [{"id": "input", "input": "input"}]},
            {"input": []},
        )
    except ValueError as exc:
        assert "prompt_template" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing prompt_template")
