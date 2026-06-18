import pytest

from abi.model_schemas import (
    ABI_EAR_GERM_ANALYSIS_SCHEMA,
    ModelValidationError,
    parse_and_validate_structured_output,
)


def test_valid_abi_ear_germ_analysis_schema_passes():
    payload = parse_and_validate_structured_output(
        """
        {
          "germ_text": "The table is still there in the morning.",
          "word_forces": [{"word": "still", "force": "marks persistence"}],
          "fertility_score": 0.5,
          "risks": ["fixture output only"]
        }
        """,
        ABI_EAR_GERM_ANALYSIS_SCHEMA,
    )

    assert payload["germ_text"] == "The table is still there in the morning."
    assert payload["word_forces"][0]["word"] == "still"
    assert payload["fertility_score"] == 0.5


def test_invalid_json_fails_validation():
    with pytest.raises(ModelValidationError, match="invalid JSON"):
        parse_and_validate_structured_output("{not json", ABI_EAR_GERM_ANALYSIS_SCHEMA)


def test_malformed_structured_output_fails_validation():
    with pytest.raises(ModelValidationError, match="word_forces must be list"):
        parse_and_validate_structured_output(
            """
            {
              "germ_text": "The table is still there in the morning.",
              "word_forces": "not a list",
              "fertility_score": 0.5,
              "risks": []
            }
            """,
            ABI_EAR_GERM_ANALYSIS_SCHEMA,
        )


def test_schema_valid_semantically_minimal_output_passes():
    payload = parse_and_validate_structured_output(
        """
        {
          "germ_text": "The table is still there in the morning.",
          "word_forces": [],
          "fertility_score": 0.0,
          "risks": []
        }
        """,
        ABI_EAR_GERM_ANALYSIS_SCHEMA,
    )

    assert payload == {
        "germ_text": "The table is still there in the morning.",
        "word_forces": [],
        "fertility_score": 0.0,
        "risks": [],
    }
