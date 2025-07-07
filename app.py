from flask import Flask, render_template, request, redirect, url_for
import subprocess
import os
import json
from pathlib import Path

app = Flask(__name__)
app.config['CONFIG_FILE'] = 'models.json'
app.config['LLAMA_SERVER'] = 'C:\\Users\\beholder\\Desktop\\llama.cpp\\llama-server.exe'

# Ensure config file exists
if not Path(app.config['CONFIG_FILE']).exists():
    with open(app.config['CONFIG_FILE'], 'w') as f:
        json.dump([], f)

# Globals to track current process
current_process = None
current_model_id = None

def get_models():
    with open(app.config['CONFIG_FILE']) as f:
        return json.load(f)

def save_models(models):
    with open(app.config['CONFIG_FILE'], 'w') as f:
        json.dump(models, f, indent=2)

@app.route('/')
def index():
    models = get_models()
    return render_template('index.html', 
                         models=models, 
                         current_process=current_process,
                         current_model_id=current_model_id)

@app.route('/start/<int:model_id>')
def start_model(model_id):
    global current_process, current_model_id
    models = get_models()
    model = models[model_id]
    
    # Stop current if running
    if current_process:
        current_process.terminate()
    
    # Start new process
    cmd = [app.config['LLAMA_SERVER'], '-m', model['file']] + model['params'].split()
    current_process = subprocess.Popen(cmd)
    current_model_id = model_id
    
    return redirect(url_for('index'))

@app.route('/stop')
def stop_model():
    global current_process, current_model_id
    if current_process:
        current_process.terminate()
        current_process = None
        current_model_id = None
    return redirect(url_for('index'))

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        models = get_models()
        models.append({
            'name': request.form['name'],
            'file': request.form['file'],
            'params': request.form['params']
        })
        save_models(models)
        return redirect(url_for('index'))
    return render_template('config.html')

@app.route('/edit/<int:model_id>', methods=['GET', 'POST'])
def edit_model(model_id):
    models = get_models()
    if request.method == 'POST':
        models[model_id] = {
            'name': request.form['name'],
            'file': request.form['file'],
            'params': request.form['params']
        }
        save_models(models)
        return redirect(url_for('index'))
    return render_template('config.html', model=models[model_id], model_id=model_id)

if __name__ == '__main__':
    app.run(debug=True)
