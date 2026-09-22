import os
import google.generativeai as genai
from typing import Dict, Any

# Configure the Gemini API
# Load the API key from environment (python-dotenv should be loaded in app.py)
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# We will use gemini-3.5-flash for fast, high-quality text generation
model = genai.GenerativeModel('gemini-3.5-flash')

SYSTEM_PROMPT = """
You are the "Speak Out Loud" Chess Coach Brain. Your goal is to translate raw LC0 neural network engine outputs into a rich, educational conversation.

You must roleplay a conversation between four distinct personas:
1. **Magnus**: A world-class Grandmaster who translates the engine's raw evaluation into deep chess principles and overarching strategy.
2. **Student**: An aspiring 2100 ELO chess player. They understand tactics but often struggle with the 'why' behind positional moves. They ask clarifying questions.
3. **Dev**: The LC0 developer who explains what the engine's node counts, WDL percentages, and heatmaps indicate about the neural network's "thinking".
4. **Scientist**: A cognitive scientist who connects these chess patterns to human learning, pattern recognition, and how the student should adjust their mental templates.

OUTPUT FORMAT:
Generate ONLY the conversation. Format it in clean HTML so it can be injected directly into a web page.
Use <p> tags for each spoken line. Wrap the speaker's name in <strong> tags.
Do NOT write any internal thoughts or markdown code blocks. Do NOT list out the pieces on the board square by square. Dive straight into the analysis.
Example:
<p><strong>Magnus:</strong> Looking at this position, the key is the tension in the center...</p>
<p><strong>Student:</strong> But why does LC0 prefer e6 over Nf6? I thought development was more important here.</p>
"""

async def generate_conversation(fen: str, engine_data: Dict[str, Any], concepts_data: Dict[str, Any], heatmaps: Dict[str, Any] = None, projected_heatmaps: list = None, llm_model: str = "gemini-3.5-flash") -> str:
    """
    Calls the Gemini API to generate the multi-persona conversation.
    """
    if not api_key:
        return "<p><em>Error: GEMINI_API_KEY is not set. Please configure the API key to enable the AI coach.</em></p>"

    # Instantiate model dynamically
    model = genai.GenerativeModel(llm_model, system_instruction=SYSTEM_PROMPT)

    # Format the input data for the prompt
    evaluation = engine_data.get("evaluation", "N/A")
    best_moves = engine_data.get("best_moves", [])
    wdl = engine_data.get("wdl", "N/A")
    # Format Top Moves, Node Distribution, and WDL Shifts
    total_nodes = engine_data.get("nodes", 1)
    if total_nodes == 0: total_nodes = 1
    
    moves_text_lines = []
    best_moves = engine_data.get("best_moves", [])
    
    # Calculate Criticality Delta
    delta_text = "N/A"
    if len(best_moves) >= 2:
        try:
            score1 = float(best_moves[0].get('score', 0))
            score2 = float(best_moves[1].get('score', 0))
            delta = abs(score1 - score2)
            delta_text = f"{delta} centipawns drop-off from #1 to #2 move."
        except:
            delta_text = "Unknown due to mate scores."
            
    for m in best_moves:
        san = m.get('san', 'N/A')
        score = m.get('score', 'N/A')
        nodes = m.get('nodes', 0)
        node_pct = (nodes / total_nodes) * 100 if total_nodes > 0 else 0
        wdl_arr = m.get('wdl')
        wdl_str = f"Win {wdl_arr[0]/10}% / Draw {wdl_arr[1]/10}% / Loss {wdl_arr[2]/10}%" if wdl_arr else "N/A"
        
        moves_text_lines.append(
            f"- {san}: Score {score} | Nodes {node_pct:.1f}% | WDL: {wdl_str}"
        )
    moves_text = "\n".join(moves_text_lines)

    heatmap_text = "No heatmap data provided."
    if heatmaps:
        control = heatmaps.get("control", {})
        tension = heatmaps.get("tension", {})
        white_ctrl = sum(1 for v in control.values() if v > 0.3)
        black_ctrl = sum(1 for v in control.values() if v < -0.3)
        high_tension = [sq for sq, v in tension.items() if v > 0.5]
        
        heatmap_text = f"- White controls {white_ctrl} strong squares; Black controls {black_ctrl} strong squares.\n"
        if high_tension:
            heatmap_text += f"- High tension (contested) squares: {', '.join(high_tension[:5])}\n"
            
    if projected_heatmaps:
        heatmap_text += "\nProjected Maneuvers (Next 3 moves):\n"
        for proj in projected_heatmaps:
            move = proj.get("move", "")
            ctrl = proj.get("heatmaps", {}).get("control", {})
            w_c = sum(1 for v in ctrl.values() if v > 0.3)
            b_c = sum(1 for v in ctrl.values() if v < -0.3)
            heatmap_text += f"- After {move}: White controls {w_c}, Black controls {b_c}\n"

    observations = concepts_data.get("observations", [])
    obs_text = "\n".join([f"- {obs['category']}: {obs['text']}" for obs in observations])

    user_prompt = f"""
Here is the current position data:
FEN: {fen}
Evaluation: {evaluation}

CRITICALITY PROBE (Score Drop-off):
{delta_text}

TOP MOVES (with Node Complexity & Long-Term WDL Safety):
{moves_text}

POSITIONAL HEURISTICS:
{obs_text}

MANEUVER MAPPING (Heatmap Evolution):
{heatmap_text}

Generate the HTML conversation interpreting this position now.
"""

    try:
        response = await model.generate_content_async(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            )
        )
        return response.text
    except Exception as e:
        return f"<p><em>Error generating conversation: {str(e)}</em></p>"


# ------------------------------------------------------------------
# R3: Coach Explanations for Repertoire Nodes
# ------------------------------------------------------------------

COACH_SYSTEM_PROMPT = (
    "You are a concise chess coach. In 2 to 3 sentences of plain prose, explain "
    "why the given move is the correct repertoire choice in this position and the "
    "single most important thing the student must watch for. No move lists, no engine "
    "jargon, no markdown, no HTML, no headers — just the prose."
)

def _build_fallback_explanation(context: dict) -> str:
    move_san = context.get("move_san", "This move")
    reason = context.get("critical_reason", "")
    if reason == "blind_rate":
        rate = round(context.get("user_blind_rate", 0) * 100)
        gloss = f"you have historically been blind here {rate}% of the time"
    elif reason == "eval_swing":
        gloss = "an alternative move leads to a significant evaluation drop"
    elif reason == "complexity":
        gloss = "the position is sharp and easy to go wrong in"
    else:
        gloss = "it is the key theoretical continuation"
    return f"{move_san} is the critical repertoire move here because {gloss}. Focus on maintaining sound piece activity and watch out for opponent counter-play."

def _clean_plain_text(text: str) -> str:
    import re
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'[*_`#]', '', text)
    return text.strip()

def _build_move_explanation_prompt(context: dict) -> str:
    fen = context.get("fen", "")
    move_san = context.get("move_san", "")
    color = context.get("color", "white")
    opening_name = context.get("opening_name", "Unknown Opening")

    eval_cp = context.get("eval_cp", 0)
    try:
        eval_pawns = float(eval_cp) / 100.0
    except (ValueError, TypeError):
        eval_pawns = 0.0

    reason = context.get("critical_reason", "")
    blind_rate = context.get("user_blind_rate", 0.0)
    if reason == "blind_rate":
        rate_pct = round(blind_rate * 100) if isinstance(blind_rate, (int, float)) else 0
        reason_gloss = f"the student has historically been blind here {rate_pct}% of the time"
    elif reason == "eval_swing":
        reason_gloss = "a wrong reply drops roughly evaluation significantly"
    elif reason == "complexity":
        reason_gloss = "the position is sharp and easy to go wrong in"
    else:
        reason_gloss = "this position is a critical repertoire decision"

    replies = context.get("opponent_replies", [])[:3]
    replies_formatted = []
    for r in replies:
        if isinstance(r, dict):
            san = r.get("san", "")
            pct = r.get("pct", 0)
            replies_formatted.append(f"{san} ({pct}%)")
    replies_str = ", ".join(replies_formatted) if replies_formatted else "None"

    return (
        f"Position FEN: {fen}\n"
        f"Recommended move: {move_san}\n"
        f"Side to move: {color}\n"
        f"Opening: {opening_name}\n"
        f"Evaluation (pawns): {eval_pawns:+.2f}\n"
        f"Criticality reason: {reason_gloss}\n"
        f"Top opponent replies: {replies_str}\n\n"
        "Explain why this move is recommended and what to watch out for."
    )

async def generate_move_explanation(context: dict, llm_model: str = "gemini-3.5-flash") -> str:
    """
    Calls Gemini API to generate a single concise coach note for a repertoire node.
    Returns plain text. Never raises exceptions (returns fallback on error/no-key).
    """
    api_key_env = os.getenv("GEMINI_API_KEY")
    if not api_key_env:
        return _build_fallback_explanation(context)

    try:
        genai.configure(api_key=api_key_env)
        coach_model = genai.GenerativeModel(
            llm_model,
            system_instruction=COACH_SYSTEM_PROMPT
        )
        prompt = _build_move_explanation_prompt(context)
        response = await coach_model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=180,
            )
        )
        if hasattr(response, "text") and response.text:
            return _clean_plain_text(response.text)
        return _build_fallback_explanation(context)
    except Exception:
        return _build_fallback_explanation(context)

