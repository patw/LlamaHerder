from flask import Flask, render_template, request, redirect, url_for
from moofile import Collection, DocumentNotFoundError
import subprocess
import os
import json
from pathlib import Path
import threading

app = Flask(__name__)

models_db = Collection('models.bson', indexes=['name'])
defaults_db = Collection('defaults.bson')

# Ensure defaults document exists
if not defaults_db.exists({}):
    defaults_db.insert({
        '_id': 'defaults',
        'llama_server': '',
        'default_options': '',
        'default_model_path': ''
    })

LOG_FILE = '/tmp/llamaherder.log'

# Globals to track current process
current_process = None
current_model_id = None

def read_process_output(process):
    try:
        with open(LOG_FILE, 'a') as f:
            for line in process.stdout:
                f.write(line)
                f.flush()
    except Exception:
        pass

def get_models():
    return models_db.find({}).to_list()

def get_defaults():
    return defaults_db.find_one({})

def save_defaults(defaults):
    if defaults_db.exists({'_id': 'defaults'}):
        defaults_db.update_one({'_id': 'defaults'}, set=defaults)
    else:
        defaults_db.insert({
            '_id': 'defaults',
            **defaults
        })

@app.route('/')
def index():
    models = get_models()
    defaults = get_defaults()
    return render_template('index.html', 
                          models=models, 
                          current_process=current_process,
                          current_model_id=current_model_id,
                          defaults=defaults)

@app.route('/start/<int:model_id>')
def start_model(model_id):
    global current_process, current_model_id
    models = get_models()
    defaults = get_defaults()
    model = models[model_id]
    
    # Resolve relative paths against default_model_path
    model_file = model['file']
    if model['file'] and not os.path.isabs(model['file']) and defaults.get('default_model_path'):
        model_file = os.path.join(defaults['default_model_path'], model['file'])
    
    mmproj_path = model.get('mmproj', '')
    if mmproj_path and not os.path.isabs(mmproj_path) and defaults.get('default_model_path'):
        mmproj_path = os.path.join(defaults['default_model_path'], mmproj_path)
    
    # Stop current if running
    if current_process:
        current_process.terminate()
    
    # Start new process
    cmd = [defaults['llama_server'], '-m', model_file]
    if mmproj_path:
        cmd += ['--mmproj', mmproj_path]
    if defaults['default_options']:
        cmd += defaults['default_options'].split()
    if model.get('params'):
        cmd += model['params'].split()
    current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    current_model_id = model_id
    open(LOG_FILE, 'w').close()
    thread = threading.Thread(target=read_process_output, args=(current_process,), daemon=True)
    thread.start()
    
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
    copy_from = request.args.get('copy_from')
    if copy_from:
        copy_from = json.loads(copy_from)
    else:
        copy_from = None

    if request.method == 'POST':
        models = get_models()
        models.append({
            'name': request.form['name'],
            'file': request.form['file'],
            'mmproj': request.form.get('mmproj', ''),
            'params': request.form['params']
        })
        # Save each model via insert (MooFile doesn't support bulk replace)
        models_db.delete_many({})
        for model in models:
            models_db.insert(model)
        return redirect(url_for('index'))
    defaults = get_defaults()
    return render_template('config.html', 
                          defaults=defaults,
                          copy_from=copy_from)

@app.route('/edit/<int:model_id>', methods=['GET', 'POST'])
def edit_model(model_id):
    models = get_models()
    if request.method == 'POST':
        # Update the model by its _id
        model = models[model_id]
        models_db.update_one(
            {'_id': model['_id']},
            set={
                'name': request.form['name'],
                'file': request.form['file'],
                'mmproj': request.form.get('mmproj', ''),
                'params': request.form['params']
            }
        )
        return redirect(url_for('index'))
    defaults = get_defaults()
    return render_template('config.html',
                          model=models[model_id],
                          model_id=model_id,
                          defaults=defaults)

@app.route('/copy/<int:model_id>')
def copy_model(model_id):
    models = get_models()
    if 0 <= model_id < len(models):
        copied = json.dumps(dict(models[model_id]))
        return redirect(url_for('config', copy_from=copied))
    return redirect(url_for('index'))

@app.route('/defaults', methods=['GET', 'POST'])
def edit_defaults():
    if request.method == 'POST':
        defaults = {
            'llama_server': request.form['llama_server'],
            'default_options': request.form['default_options'],
            'default_model_path': request.form['default_model_path']
        }
        save_defaults(defaults)
        return redirect(url_for('index'))
    defaults = get_defaults()
    return render_template('defaults.html', defaults=defaults)

@app.route('/delete/<int:model_id>', methods=['POST'])
def delete_model(model_id):
    global current_model_id
    models = get_models()
    if 0 <= model_id < len(models):
        model = models[model_id]
        models_db.delete_one({'_id': model['_id']})
        if current_model_id == model_id:
            current_model_id = None
        elif current_model_id is not None and current_model_id > model_id:
            current_model_id -= 1
    return redirect(url_for('index'))

@app.route('/logs')
def view_logs():
    lines = []
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        lines = [line.rstrip('\n') for line in lines[-200:]]
    except FileNotFoundError:
        pass
    return render_template('logs.html', lines=lines, log_file=LOG_FILE)

if __name__ == '__main__':
    app.run(debug=True)
