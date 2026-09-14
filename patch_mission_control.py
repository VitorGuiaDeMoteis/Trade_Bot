import re
with open("services/api/mission_control.py", "r") as f:
    text = f.read()

new_logic = """    mode = getattr(request.app.state, "mission_control_mode", "broker")
    if mode == "replay":
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="replay">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "REPLAY LIVE — SIMULAÇÃO HISTÓRICA")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M4 / HISTORICAL REPLAY")
        return HTMLResponse(page, headers=headers)
    elif mode == "night_lab":
        page = PAGE.read_text(encoding="utf-8").replace("<body>", '<body data-mode="night_lab">')
        page = page.replace("ALPACA PAPER — DINHEIRO VIRTUAL", "NIGHT LAB — SIMULAÇÃO EM LOTE")
        page = page.replace("M7 / BROKER OBSERVABILITY", "M8 / NIGHT LAB EXPERIMENT")
        return HTMLResponse(page, headers=headers)
    return FileResponse(PAGE, media_type="text/html", headers=headers)"""

text = re.sub(r'    if getattr\(request.app.state, "mission_control_mode", "broker"\) == "replay":\n.*?(?=    return FileResponse)', new_logic, text, flags=re.DOTALL)
with open("services/api/mission_control.py", "w") as f:
    f.write(text)
