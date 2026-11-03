# JARVIS-AI-ASSISTANT


New JARVIS AI Intelligent Assistant with fully offline speech recognition, advanced local LLM reasoning, and a high-tech Graphical User Interface.

A truly autonomous UI for J.A.R.V.I.S that runs in a borderless Chromium-based window.

---

## About JARVIS
Jarvis is originally an AI which was introduced in the Iron Man movie series. Using this repository, you can bring your own Jarvis to life! This is a completely python-based program equipped with a local Llama 3.2 engine to provide hyper-realistic, conversational AI on your desktop.

J.A.R.V.I.S. – JUST A RATHER VERY INTELLIGENT SYSTEM

## Specialty of JARVIS
- Fully autonomous with local Llama 3.2 logic.
- Ultra-fast offline speech recognition using your local microphone.
- Offline Text-to-Speech service so your data stays fully private.
- Voice-based program launching, URL opening, and keystroke automation.
- **Beautiful, animated Iron-Man style Sci-Fi GUI!**

---

## Setup Procedures

For getting JARVIS up and running, the step-by-step instructions are given below. 

### Full Installation Guide
Open your terminal (Command Prompt, PowerShell, or Git Bash) and follow these exact steps to install and configure everything from scratch:

**1. Install Python**
*For Windows (PowerShell/CMD):*
```bash
winget install Python.Python.3.10
```
*For Linux/Ubuntu:*
```bash
sudo apt update && sudo apt install python3 python3-pip
```

**2. Install the Ollama Engine**
*For Windows (PowerShell/CMD):*
```bash
winget install Ollama.Ollama
```
*For Linux/Mac:*
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**3. Clone the repository and enter the directory:**
```bash
git clone https://github.com/Ammaribrahimbinumar/AI-JARVIS-ASSISTANT-OFFLINE-MODE.git
cd AI-JARVIS-ASSISTANT-OFFLINE-MODE
```

**4. Install the required Python modules:**
```bash
pip install -r requirements.txt
```
*(Note for Windows: If you run into red text issues installing PyAudio, run `pip install pipwin` then `pipwin install pyaudio`.)*

**5. Get the AI Tracking Model:**
Ensure the Ollama application is running in the background, then download the neural weights for our model:
```bash
ollama pull llama3.2:3b
```
*(This may take a few minutes depending on your internet connection.)*

---

### Running the Program
Once everything is installed, starting the assistant is as simple as running:

```bash
python server.py
```

This will instantly boot up the threaded Python backend, activate your microphone, and spawn the frameless animated sci-fi HUD on your desktop! You can now start talking!
