# 🏭 Industrial Digital Optimus

Replicación de la arquitectura Digital Optimus (Macrohard) aplicada al sector industrial. Utiliza **LangChain Deep Agents** con subagentes System-1/System-2 y captura real de pantalla del host Windows.

## Arquitectura

```
[Windows Host] → screenshots → [Docker: FastAPI API] → [Docker: LangChain Agents]
                               [Docker: Gradio UI]   ←  status / results
[Windows Host] ← actions    ← [Docker: FastAPI API]
```

## Inicio Rápido

### 1. Configura el `.env`
```bash
cp .env.example .env
# Edita .env con tus API keys
```

### 2. Levanta Docker
```bash
docker-compose up --build
```
Servicios disponibles:
- **Gradio UI**: http://localhost:7860
- **FastAPI Docs**: http://localhost:8000/docs
- **Agents API**: http://localhost:8001/docs

### 3. Inicia el Cliente Windows
En una terminal separada en **Windows** (fuera de Docker):
```bash
cd windows_client
pip install -r requirements.txt
python client.py
```

## Componentes

| Componente | Ubicación | Propósito |
|---|---|---|
| FastAPI Bridge | `api/` | Puente HTTP: screenshots, alertas, acciones |
| Deep Agents Core | `agents/` | Sistema-1 + Sistema-2 con LangChain |
| Gradio Dashboard | `ui/` | Interfaz visual de monitoreo |
| Windows Client | `windows_client/` | Captura pantalla + ejecuta acciones |

## Alertas Industriales Disponibles

- 🌡️ Alta Temperatura — Bomba #3
- ⚡ Vibración Anómala — Motor A2
- 🔴 Presión Crítica — Tubería P-07
- 📡 Falla de Comunicación — PLC-Sector C
- 💧 Nivel Bajo — Tanque T-01
