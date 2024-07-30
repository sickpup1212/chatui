from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import asyncio
import json
import os
import psycopg2
import openai
from openai import OpenAI
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret!'
database_url = os.getenv("DATABASE")
socketio = SocketIO(app)
openai_api_key = os.getenv("OPENAI_API_KEY")

db_tools ="asst_n5rvkEBJkxP4ICILxkjK1Zq7"
soup_kitchen = "asst_PfIxoXIQOUGbr0DLuqwNbpyP"

class Database:
    def __init__(self, conn_string):
        self.conn = psycopg2.connect(conn_string)
        self.cur = self.conn.cursor()

    def execute_query(self, query, data=None):
        try:
            if data:
                self.cur.execute(query, data)
            else:
                self.cur.execute(query)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e

    def fetch_one(self, query, data=None):
        try:
            if data:
                self.cur.execute(query, (data,))
            else:
                self.cur.execute(query)
            return self.cur.fetchone()
        except Exception as e:
            self.conn.rollback()
            raise e

    def fetch_all(self, query, data=None):
        try:
            if data:
                self.cur.execute(query, (data,))
            else:
                self.cur.execute(query)
            return self.cur.fetchall()
        except Exception as e:
            self.conn.rollback()
            raise e

    def close(self):
        self.cur.close()
        self.conn.close()

    def get_column_names(self, table_name):
        query = "SELECT column_name FROM information_schema.columns WHERE table_name = %s;"
        columns = self.fetch_all(query, table_name)
        return [col[0] for col in columns]

class OpenAIService:
    def __init__(self, api_key, thread=None):
        self.openai = openai.OpenAI(api_key=api_key)
        if thread != None:
            self.thread = self.openai.beta.threads.retrieve(thread)
        else:
            self.thread = self.openai.beta.threads.create()
        socketio.emit('show_thread', {'current_threadID': self.thread.id})

    async def poll_answers(self, thread_id, run_id):
        completed = False
        
        while not completed:
            response = self.openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            socketio.emit('status_update', {
                'status': response.status,
                'id': response.id,
                'created_at': response.created_at,
                'completed_at': response.completed_at
            })
            if response.status in ['completed', 'expired']:
                message = self.openai.beta.threads.messages.list(thread_id)
                outgoing_messages = message.data[0].content[0].text.value
                completed = True
                socketio.emit('chat_message', {'message': f'<span class="username">Assistant: <p class="regtext">{outgoing_messages}</p></span>'})
            elif response.status == 'requires_action':
                await self.handle_required_action(response, thread_id, run_id)
            elif response.status in ['failed', 'cancelled', 'cancelling']:
                completed = True
            await asyncio.sleep(2) if response.status in ['in_progress', 'queued'] else None

    async def handle_required_action(self, response, thread_id, run_id):
        tool_outputs = []
        for tool_call in response.required_action.submit_tool_outputs.tool_calls:
            if tool_call.function.name == "get_soup_text":
                output = get_soup_text(json.loads(tool_call.function.arguments)['url'], json.loads(tool_call.function.arguments)['tag'])
            elif tool_call.function.name == 'execute_and_commit_only_no_fetch':
                output = execute_and_commit_only_no_fetch(json.loads(tool_call.function.arguments)['query'])
            elif tool_call.function.name == 'get_database_info':
                output = get_database_info()
            elif tool_call.function.name == 'create_html_table':
                output = create_html_table(json.loads(tool_call.function.arguments)['db_table_name'])
            elif tool_call.function.name == 'execute_and_fetch_all':
                output = execute_and_fetch_all(json.loads(tool_call.function.arguments)['query'])
            else:
                output = 'There is a problem, function not found!'
            tool_outputs.append({'tool_call_id': tool_call.id, 'output': str(output)})
        self.openai.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run_id, tool_outputs=tool_outputs)

    def handle_create_message(self, message):
        self.openai.beta.threads.messages.create(thread_id=self.thread.id, role='user', content=message)
        socketio.emit('chat_message', {'message': f'<span class="username">User: <p class="regtext">{message}</p></span>' })

    def handle_run_step(self, assistant_id):
        run = self.openai.beta.threads.runs.create(thread_id=self.thread.id, assistant_id=assistant_id)
        asyncio.run(self.poll_answers(self.thread.id, run.id))

def get_table_names():
    db = Database(database_url)
    try:
        tables = db.fetch_all("SELECT tablename FROM pg_tables WHERE schemaname='public';")
        return [table[0] for table in tables]
    finally:
        db.close()

def get_rows(table_name):
    db = Database(database_url)
    try:
        return db.fetch_all(f"SELECT * FROM {table_name};")
    finally:
        db.close()

def get_database_info():
    db = Database(database_url)
    table_info = []
    try:
        table_names = get_table_names()
        for table_name in table_names:
            columns = db.get_column_names(table_name)
            table_info.append({"table_name": table_name, "column_names": columns})
    finally:
        db.close()
    return table_info

def get_soup_text(url: str, tag: str) -> str:
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    if tag == "img":
        return " ".join([f"<img src='{img['src']}' alt='ok'>" for img in soup.find_all(tag)])
    else:
        return " ".join([element.text for element in soup.find_all(tag)])

def full_table_data(table_name):
    return {
        'table': table_name,
        'columns': get_column_names(table_name),
        'rows': get_rows(table_name)
    }

def create_html_table(db_table_name):
    db_table = full_table_data(db_table_name)
    html_table = "<table>\n  <tr>\n" + "".join([f"    <th>{col}</th>\n" for col in db_table['columns']]) + "  </tr>\n"
    for row in db_table['rows']:
        html_table += "  <tr>\n" + "".join([f"    <td>{value}</td>\n" for value in row]) + "  </tr>\n"
    return html_table + "</table>"

def execute_and_commit_only_no_fetch(query):
    db = Database(database_url)
    try:
        db.execute_query(query)
        return 'query successful'
    except Exception as e:
        return f"query failed with error: {e}"
    finally:
        db.close()

def execute_and_fetch_one(query):
    db = Database(database_url)
    try:
        return db.fetch_one(query)
    except Exception as e:
        return f"query failed with error: {e}"
    finally:
        db.close()

def execute_and_fetch_all(query):
    db = Database(database_url)
    try:
        return db.fetch_all(query)
    except Exception as e:
        return f"query failed with error: {e}"
    finally:
        db.close()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('status_update')
def handle_status_update(data):
    emit('status_update', {'status': data['status'], 'id': data['id']})

@socketio.on('chat_message')
def handle_chat_message(data):
    emit('chat_message', {'message': data['message']})

@socketio.on('show_thread')
def handle_show_thread(data):
    emit('show_thread', {'current_threadID': data['current_threadID']})

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    socketio.emit('status_update', data)
    return jsonify({"message": "Status update emitted"}), 200

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    socketio.emit('chat_message', data)
    return jsonify({"message": data['message']}), 200

@app.route('/display_thread', methods=['POST'])
def show_thread():
    data = request.json
    socketio.emit('show_thread', data)
    return jsonify({"message": "Thread message emitted"}), 200

@app.route('/new_thread', methods=['POST', 'GET'])
def new_thread():
    service = OpenAIService(api_key=openai_api_key)
    return jsonify({"current_threadID": service.thread.id})

"""
@app.route('/new_assistant', methods=['POST', 'GET'])
def new_assistant():
    new_assistant_id = "new_assistant_id"  
    socketio.emit('show_assistant', {'current_assistantID': current_assistant_id})
    return jsonify({"current_assistantID": current_assistant_id})
"""

@app.route('/assistants/list', methods=['GET'])
def listAssistant():
    client = OpenAI(api_key=openai_api_key)
    liz = client.beta.assistants.list()
    linklist=""
    list_of_assistants = liz.dict()['data']
    for i in list_of_assistants:
        asstID= i['id']
        asstName = i['name']
        elm = f'<a id="{asstID}" href="#">{asstName}</a><br>'
        linklist+=elm
    
    return linklist

@app.route('/assistants/retrieve/<assistant_id>', methods=['POST'])
def retrieve_assistant(assistant_id):
    socketio.emit('show_assistant', {'current_assistantID': assistant_id})
    return jsonify({"current_assistantID": assistant_id})


@app.route('/msg_assistant', methods=['POST'])
def msg_assistant():
    data = request.json
    message = data.get('message')
    print(message)
    aid = data.get('assieID')
    print(aid)
    teenus = data.get('thread_dizzle')
    print(teenus)
    if teenus:
        service = OpenAIService(api_key=openai_api_key, thread = teenus)
    else:
        service = OpenAIService(api_key=openai_api_key)
    service.handle_create_message(message)
    service.handle_run_step(aid)
    return jsonify({"message": "Chat message emitted"}), 200

@app.route('/msg_assistant/<asstid>', methods=['POST'])
def assistant(asstid):
    data = request.json
    message = data.get('message')
    service = OpenAIService(api_key=openai_api_key)
    service.handle_create_message(message)
    socketio.emit('show_assistant', {'current_assistantID': asstid})
    service.handle_run_step(asstid)
    return redirect(url_for('index'))

if __name__ == '__main__':
    socketio.run(app, debug=True)
