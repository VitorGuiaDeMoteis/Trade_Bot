import json
import os
import urllib.request
import urllib.error
from decimal import Decimal
from sqlalchemy import text
from services.api.config import Settings
from services.api.database import create_database_engine
from services.api.analytics import get_session_analytics

def get_ai_analysis(session_json: str) -> str:
    prompt = f"""
Você é um AI Analyst. Analise o seguinte relatório JSON de uma sessão de paper trading.
Produza um relátorio contendo:
- Resumo da sessão
- Padrões observados
- Erros operacionais
- Ativos que performaram melhor/pior
- Pontos para investigar
- Sugestões de experimentos

Dados:
{session_json}
"""
    # Ollama fallback
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({
                "model": "llama3",
                "prompt": prompt,
                "stream": False
            }).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result.get("response", "Erro na resposta do Ollama")
    except Exception as e:
        return f"AI Analyst offline (Ollama falhou: {e}). O JSON acima é tudo que temos."

def main():
    settings = Settings()
    engine = create_database_engine(settings)
    with engine.connect() as conn:
        latest_run = conn.execute(
            text("SELECT run_id FROM paper_runs ORDER BY created_at DESC LIMIT 1")
        ).scalar()
        
        if not latest_run:
            print("Nenhuma sessão encontrada.")
            return
            
        data = get_session_analytics(conn, latest_run)
        
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    print("--- JSON DA SESSÃO ---")
    print(json_data)
    print("\n--- RELATÓRIO DO AI ANALYST ---")
    
    report = get_ai_analysis(json_data)
    print(report)

if __name__ == "__main__":
    main()
