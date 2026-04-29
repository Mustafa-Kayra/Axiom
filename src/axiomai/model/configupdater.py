import re
from pathlib import Path

def add_model_to_config(model_dict):
    config_path = Path(__file__).parent / "config.py"
    content = config_path.read_text(encoding="utf-8")

    # MODELS listesinin başladığı yeri bul
    # Listeye yeni bir sözlük girdisi ekle
    model_entry = (
        f'    {{"id": "{model_dict["id"]}", "name": "{model_dict["name"]}", '
        f'"max_prompt_kb": {model_dict["max_prompt_kb"]}, '
        f'"max_output_tokens": {model_dict["max_output_tokens"]}, '
        f'"context_target_kb": {model_dict["context_target_kb"]}}},\n'
    )

    # MODELS = [ satırından hemen sonrasına ekle
    new_content = re.sub(r'(MODELS = \[\n)', r'\1' + model_entry, content)
    
    config_path.write_text(new_content, encoding="utf-8")