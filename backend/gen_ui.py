import re

def generate_ui_from_prompt(prompt: str) -> str:
    """
    A heuristic-based 'Gen UI' engine that converts natural language prompts
    into HTML form components.
    """
    prompt = prompt.lower()
    html = ""

    # Heuristic 1: Text Inputs
    if "text" in prompt or "input" in prompt or "field" in prompt:
        label = "Input"
        if "patient" in prompt: label = "Patient Name"
        if "history" in prompt: label = "Patient History"
        if "comment" in prompt: label = "Comments"
        if "age" in prompt: label = "Age"
        
        if "long" in prompt or "area" in prompt or "history" in prompt or "comment" in prompt:
            html = f'''
            <div class="form-group">
                <label>{label} (AI Generated)</label>
                <textarea class="gen-input" rows="3" style="width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 4px;"></textarea>
            </div>'''
        else:
            html = f'''
            <div class="form-group">
                <label>{label} (AI Generated)</label>
                <input type="text" class="gen-input" style="width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 4px;">
            </div>'''

    # Heuristic 2: Checkboxes / Toggles
    elif "check" in prompt or "box" in prompt or "agree" in prompt or "consent" in prompt:
        label = "Consent"
        if "confirm" in prompt: label = "Confirmation"
        if "agree" in prompt: label = "I agree to terms"
        
        html = f'''
        <div class="form-group" style="display: flex; align-items: center; gap: 10px;">
            <input type="checkbox" id="gen-check">
            <label for="gen-check" style="margin: 0;">{label} (AI Generated)</label>
        </div>'''

    # Heuristic 3: Sliders / Range
    elif "slider" in prompt or "range" in prompt or "threshold" in prompt:
        label = "Threshold"
        if "confidence" in prompt: label = "Confidence Threshold"
        
        html = f'''
        <div class="form-group">
            <label>{label} (AI Generated)</label>
            <input type="range" min="0" max="100" style="width: 100%;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #6b778c;">
                <span>0%</span><span>50%</span><span>100%</span>
            </div>
        </div>'''

    # Heuristic 4: Select / Dropdown
    elif "select" in prompt or "dropdown" in prompt or "option" in prompt or "choose" in prompt or "gender" in prompt or "type" in prompt or "color" in prompt:
        label = "Selection"
        options = ["Option 1", "Option 2", "Option 3"]
        
        if "gender" in prompt: 
            label = "Gender"
            options = ["Male", "Female", "Other"]
        if "eye" in prompt and "color" not in prompt:
            label = "Eye"
            options = ["Left", "Right"]
        if "color" in prompt:
            label = "Color"
            options = ["Blue", "Brown", "Green", "Hazel", "Grey", "Other"]
            if "eye" in prompt: label = "Eye Color"
        if "blood" in prompt:
            label = "Blood Type"
            options = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
            
        opts_html = "".join([f'<option>{o}</option>' for o in options])
        
        html = f'''
        <div class="form-group">
            <label>{label} (AI Generated)</label>
            <select style="width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 4px;">
                {opts_html}
            </select>
        </div>'''
        
    # Fallback
    else:
        html = f'''
        <div class="form-group">
            <label>Custom Field (AI Generated)</label>
            <div style="padding: 10px; background: #f0f0f0; border-radius: 4px; font-size: 12px;">
                Could not fully understand "{prompt}", but here is a generic container.
            </div>
        </div>'''

    return html
