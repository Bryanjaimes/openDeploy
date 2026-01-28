import os

try:
    import google.generativeai as genai
except Exception:
    genai = None

def generate_ui_from_prompt(prompt: str) -> str:
    """
    Generates UI components using Google Gemini API if available,
    otherwise falls back to heuristic rules.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    # 1. If no API key, use the "dumb" logic (Heuristics)
    if not api_key or genai is None:
        print("No GEMINI_API_KEY found. Using heuristics.")
        return heuristic_generate(prompt)

    # 2. If API key exists, use the "smart" logic (LLM)
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # Strict instructions to the LLM to only return HTML
        system_instruction = """
        You are an expert Frontend Developer. 
        Generate a single valid HTML <div> component using inline CSS styles (no external classes like Tailwind unless specified, prefer standard style attributes for portability).
        - Do NOT wrap in ```html code blocks.
        - Do NOT include <html> or <body> tags.
        - Do NOT add explanations.
        - Make it look professional and medical-grade.
        - Ensure input fields have appropriate labels.
        """
        
        response = model.generate_content(f"{system_instruction}\nUser Request: {prompt}")
        return response.text.strip().replace("```html", "").replace("```", "")
        
    except Exception as e:
        print(f"LLM Error: {e}")
        return heuristic_generate(prompt)

def heuristic_generate(prompt: str):
    """
    Fallback logic for when the LLM is unavailable.
    """
    p = prompt.lower()

    # Rule 1: Patient History
    if "history" in p or "notes" in p or "description" in p:
        return """
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px; font-weight: 500; font-size: 14px; color: #6b778c;">Patient History / Notes</label>
            <textarea style="width: 100%; padding: 8px; border: 1px solid #dfe1e6; border-radius: 4px;" rows="3" placeholder="Enter patient background..."></textarea>
        </div>
        """

    # Rule 2: Sliders
    if "slider" in p or "threshold" in p or "confidence" in p:
        return """
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px; font-weight: 500; font-size: 14px; color: #6b778c;">Confidence Threshold</label>
            <div style="display: flex; align-items: center;">
                <input type="range" min="0" max="100" value="50" style="width: 100%;">
                <span style="margin-left: 10px; font-size: 12px; color: #6b778c;">50%</span>
            </div>
        </div>
        """

    # Rule 3: Checkboxes
    if "check" in p or "consent" in p or "agree" in p:
        return """
        <div class="form-group" style="margin-bottom: 15px; display: flex; align-items: center;">
            <input type="checkbox" style="margin-right: 10px;">
            <label style="font-size: 14px; color: #172b4d;">Patient Consent / Verification</label>
        </div>
        """
    
    # Rule 4: Dropdowns
    if "eye color" in p:
        return """
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px; font-weight: 500; font-size: 14px; color: #6b778c;">Eye Color</label>
            <select style="width: 100%; padding: 8px; border: 1px solid #dfe1e6; border-radius: 4px;">
                <option>Brown</option>
                <option>Blue</option>
                <option>Green</option>
                <option>Hazel</option>
                <option>Other</option>
            </select>
        </div>
        """

    # Fallback
    return f"""
    <div class="form-group" style="margin-bottom: 15px;">
        <label style="display: block; margin-bottom: 5px; font-weight: 500; font-size: 14px; color: #6b778c;">Custom Field: {prompt}</label>
        <input type="text" style="width: 100%; padding: 8px; border: 1px solid #dfe1e6; border-radius: 4px;" placeholder="Enter value...">
    </div>
    """
