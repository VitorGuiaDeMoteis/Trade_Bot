with open("services/api/mission_control.py", "r") as f:
    text = f.read()

import re

ai_html = """<div class="metric"><div class="label">AI Observer</div><div id="ai-status" class="value" style="font-size: 16px;">—</div><small id="ai-desc">Aguardando inferência</small></div>"""
ai_js = """
  if (data.ai_status) {
    let aiBox = document.getElementById('ai-status');
    if (!aiBox) {
        let metrics = document.getElementById('metrics');
        let div = document.createElement('div');
        div.className = 'metric';
        div.innerHTML = '<div class="label">AI Observer</div><div id="ai-status" class="value" style="font-size: 14px;">—</div><small id="ai-desc">Aguardando inferência</small>';
        metrics.appendChild(div);
        aiBox = document.getElementById('ai-status');
    }
    
    if (data.ai_status !== "OK") {
        aiBox.textContent = data.ai_status;
        aiBox.className = "value bad";
        document.getElementById('ai-desc').textContent = "Inativo ou Degraded";
    } else if (data.last_ai_observation) {
        let obs = data.last_ai_observation;
        let agreement = (data.strategy_signal === obs.regime) ? "AGREEMENT" : "DIVERGENCE";
        aiBox.textContent = `${obs.regime} (${(obs.confidence * 100).toFixed(0)}%)`;
        aiBox.className = "value " + (agreement === "AGREEMENT" ? "good" : "warn");
        document.getElementById('ai-desc').textContent = `Strategy: ${data.strategy_signal} | ${agreement}`;
    }
  }
"""

replacement = """    elif mode == "night_lab":
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="replay">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "NIGHT LAB — SIMULAÇÃO EM LOTE")
        page = page.replace("M7 / BROKER OBSERVABILITY / LOCAL DESK", "M8 / NIGHT LAB EXPERIMENT / OLLAMA AI")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M8 / NIGHT LAB EXPERIMENT")
        
        # Inject AI Javascript
        page = page.replace("renderReplay(data) {", "renderReplay(data) {\\n" + ai_js.replace('\\n', '\\\\n').replace('"', '\\\\"'))
        return HTMLResponse(page, headers=headers)"""

# I need a safer way to inject Javascript. Let's just do it directly in the text!
with open("services/api/static/mission-control.html", "r") as f:
    html = f.read()

if "data.ai_status" not in html:
    html = html.replace("renderReplay(data) {", "renderReplay(data) {\n" + ai_js)
    with open("services/api/static/mission-control.html", "w") as f:
        f.write(html)
