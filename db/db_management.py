# db_management.py
from google.cloud import firestore
from db.firebase_config import db
from datetime import datetime, timedelta
import uuid
from google.cloud.firestore_v1.base_query import FieldFilter, BaseCompositeFilter # type: ignore


def add_path(name: str, duration_weeks: int) -> str:
    paths_ref = db.collection('paths')
    new_path_ref = paths_ref.document()
    path_data = {
        'name': name,
        'duration_weeks': duration_weeks,
        'channels': [],
        'topics': [],
        'created_at': datetime.utcnow().isoformat()
    }
    new_path_ref.set(path_data)
    return new_path_ref.id


# Helper Functions
def get_all_paths():
    paths_ref = db.collection('paths')
    paths = paths_ref.stream()
    return [(path.id, path.to_dict().get('name')) for path in paths]


def get_path_by_channel(channel_id):
    doc = db.collection('channels').document(str(channel_id)).get()
    if doc.exists:
        path_id = doc.to_dict().get('path_id')
        path_name = doc.to_dict().get('path_name')
        return path_id, path_name
    return None


def add_path_to_user(member, channel_id):
    user_ref = db.collection('users').document(str(member.id))
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        user_paths = user_data.get('paths', [])
        if str(channel_id) not in user_paths:
            user_paths.append(str(channel_id))
            user_ref.update({'paths': user_paths})
    else:
        user_ref.set({'paths': [str(channel_id)]})



def add_channel_to_path(path_id, channel_id, channel_name, start_date):
    path_ref = db.collection('paths').document(path_id)
    path_doc = path_ref.get()

    if not path_doc.exists:
        raise ValueError("Path not found")

    path_data = path_doc.to_dict()
    path_channels = path_data.get('channels', [])

    channel_id_str = str(channel_id)

    print(f"Before adding: {path_channels}")

    if channel_id_str in path_channels:
        raise ValueError("Channel already linked to this path")

    path_channels.append(channel_id_str)
    print(f"After adding: {path_channels}")

    path_ref.update({
        'channels': path_channels
    })

    path_name = path_data.get('name')

    channel_ref = db.collection('channels').document(channel_id_str)
    channel_ref.set({
        'name': channel_name,
        'path_id': path_id,
        'path_name': path_name, 
        'start_date': start_date
    }, merge=True)

    print(f"Added channel {channel_id_str} to path {path_id} with start date {start_date}")




def remove_channel_from_path(path_id, channel_id):
    channel_id_str = str(channel_id)
    path_ref = db.collection('paths').document(path_id)
    path_doc = path_ref.get()

    if path_doc.exists:
        path_data = path_doc.to_dict()
        path_channels = path_data.get('channels', [])
        
        print(f"Current channels for path {path_id}: {path_channels}")  # Debugging info

        if channel_id_str in path_channels:
            path_channels.remove(channel_id_str)
            path_ref.update({'channels': path_channels})
            print(f"Removed channel {channel_id_str} from path {path_id}")
        else:
            print(f"Channel {channel_id_str} not found in path {path_id}")
    else:
        print(f"Path {path_id} does not exist")



def get_path_duration(path_id):
    path_doc = db.collection('paths').document(path_id).get()
    if path_doc.exists:
        path_data = path_doc.to_dict()
        return path_data.get('duration_weeks', 0)
    return 0

def add_topic(path_id, week, topic_name, description=None):
    topic_id = str(uuid.uuid4())
    topic_ref = db.collection('paths').document(path_id).collection('topics').document(topic_id)
    topic_ref.set({
        'name': topic_name,
        'week': week,
        'description': description or "",
        'tasks': []
    })
    print(f"Added topic {topic_name} to path {path_id}, week {week}")
    return topic_id



def record_function_usage(user_id, function_name, channel_id=None):
    user_id = str(user_id)  # Ensure user_id is a string
    usage_ref = db.collection('function_usage').document(user_id)
    usage_data = {
        "user_id": user_id,
        "function_name": function_name,
        "timestamp": firestore.SERVER_TIMESTAMP
    }
    if channel_id:
        usage_data["channel_id"] = channel_id
    usage_ref.set(usage_data, merge=True)



def get_command_metrics_by_path(start_date=None, end_date=None):
    metrics = {}

    query = db.collection('function_usage')
    if start_date:
        query = query.where('timestamp', '>=', start_date)
    if end_date:
        query = query.where('timestamp', '<=', end_date)
    
    results = query.stream()

    for result in results:
        data = result.to_dict()
        path_id = data.get('path_id')
        command = data.get('function_name')

        if path_id not in metrics:
            metrics[path_id] = {}

        if command not in metrics[path_id]:
            metrics[path_id][command] = 0

        metrics[path_id][command] += 1

    return metrics


def get_command_metrics_by_channel(start_date=None, end_date=None):
    metrics = {}

    query = db.collection('function_usage')
    if start_date:
        query = query.where('timestamp', '>=', start_date)
    if end_date:
        query = query.where('timestamp', '<=', end_date)
    
    results = query.stream()

    for result in results:
        data = result.to_dict()
        channel_id = data.get('channel_id')
        command = data.get('function_name')

        if channel_id not in metrics:
            metrics[channel_id] = {}

        if command not in metrics[channel_id]:
            metrics[channel_id][command] = 0

        metrics[channel_id][command] += 1

    return metrics


def update_start_date(channel_id, new_start_date):
    db.collection('channels').document(str(channel_id)).update({
        'start_date': new_start_date
    })

    

def get_user_week(user_id, path_id):
    doc = db.collection('user_progress').document(f'{user_id}_{path_id}').get()
    if doc.exists:
        return doc.to_dict().get('week', 1)
    return 1

def get_topics(path_id, week):
    topics_ref = db.collection('paths').document(path_id).collection('topics')
    query = topics_ref.where('week', '==', week)
    docs = query.stream()
    
    topics = []
    for doc in docs:
        topic_data = doc.to_dict()
        topic_data['topic_id'] = doc.id  # Add the topic ID to the data
        topics.append(topic_data)
        
    return topics


def get_all_tasks_for_path(path_id):
    path_doc = db.collection('paths').document(path_id).get()
    if not path_doc.exists:
        return []
    
    path_data = path_doc.to_dict()
    tasks = []
    for topic in path_data.get('topics', []):
        tasks.extend(topic.get('tasks', []))
    
    return tasks


def get_user_tasks(user_id):
    user_tasks = []
    query = db.collection('user_tasks').where(filter=FieldFilter('user_id', '==', str(user_id)))
    docs = query.stream()
    for doc in docs:
        data = doc.to_dict()
        if data.get('task_id') and data.get('completed') is not None:
            user_tasks.append((data['task_id'], data['completed'], data.get('proof_url', '')))
    return user_tasks

def get_user_tasks_by_path(user_id, path_id):
    user_tasks_ref = db.collection('users').document(str(user_id)).collection('tasks')
    user_tasks = user_tasks_ref.where('path_id', '==', path_id).stream()
    user_tasks_list = [{'task_id': task.id, **task.to_dict()} for task in user_tasks]
    print(f"User {user_id} tasks for path {path_id}: {user_tasks_list}")  # Debugging
    return user_tasks_list

    
# Utility functions
def get_task_name(task_id):
    task_ref = db.collection('tasks').document(task_id)
    task_doc = task_ref.get()
    if task_doc.exists:
        task_data = task_doc.to_dict()
        return task_data.get('name')
    return None


def delete_task(task_id, path_id, topic_id):
    task_ref = db.collection('tasks').document(task_id)
    task_doc = task_ref.get()

    if task_doc.exists:
        # Remove task ID from the corresponding topic in the path
        topic_ref = db.collection('paths').document(path_id).collection('topics').document(topic_id)
        topic_doc = topic_ref.get()
        if topic_doc.exists:
            topic_data = topic_doc.to_dict()
            tasks = topic_data.get('tasks', [])
            if task_id in tasks:
                tasks.remove(task_id)
                topic_ref.update({'tasks': tasks})

        # Delete the task document
        task_ref.delete()
        print(f"Deleted task {task_id}")
    else:
        print(f"Task {task_id} not found")



def delete_topic(topic_id):
    topic_ref = db.collection('paths').where('topics', 'array-contains', topic_id).stream()
    for path in topic_ref:
        path_ref = db.collection('paths').document(path.id).collection('topics').document(topic_id)
        topic_doc = path_ref.get()

        if topic_doc.exists:
            # Delete associated tasks
            topic_data = topic_doc.to_dict()
            task_ids = topic_data.get('tasks', [])
            for task_id in task_ids:
                db.collection('tasks').document(task_id).delete()

            # Delete the topic document
            path_ref.delete()
            print(f"Deleted topic {topic_id}")
        else:
            print(f"Topic {topic_id} not found")
                   

def delete_path(path_id):
    path_ref = db.collection('paths').document(path_id)
    path_doc = path_ref.get()

    if path_doc.exists:
        # Delete associated topics and tasks
        topics_ref = path_ref.collection('topics').stream()
        for topic in topics_ref:
            topic_data = topic.to_dict()
            task_ids = topic_data.get('tasks', [])
            for task_id in task_ids:
                db.collection('tasks').document(task_id).delete()
            path_ref.collection('topics').document(topic.id).delete()

        # Delete the path document
        path_ref.delete()
        print(f"Deleted path {path_id}")
    else:
        print(f"Path {path_id} not found")



def get_total_tasks(path_id):
    query = db.collection('tasks').where(filter=FieldFilter('path_id', '==', path_id))
    docs = query.stream()
    total_tasks = 0
    for doc in docs:
        total_tasks += 1
    return total_tasks


def get_weeks_for_path(path_id):
    query = db.collection('topics').where(filter=FieldFilter('path_id', '==', path_id))
    docs = query.stream()
    return sorted(set(doc.to_dict().get('week') for doc in docs))





def get_path_name(path_id):
    # Implement this function to get the path name from the database using the path_id
    path_doc = db.collection('paths').document(path_id).get()
    if path_doc.exists:
        return path_doc.to_dict().get('name')
    return None

def get_start_date(channel_id):
    doc = db.collection('channels').document(str(channel_id)).get()
    if doc.exists:
        return doc.to_dict().get('start_date')
    return None



def get_command_metrics(start_date=None, end_date=None):
    query = db.collection('function_usage')
    if start_date:
        query = query.where('timestamp', '>=', start_date)
    if end_date:
        query = query.where('timestamp', '<=', end_date)
    
    docs = query.stream()
    metrics = {}
    
    for doc in docs:
        data = doc.to_dict()
        function_name = data.get('function_name')
        
        if function_name not in metrics:
            metrics[function_name] = 0
        
        metrics[function_name] += 1
    
    return metrics


def is_admin(member):
    admin_roles = ["admin", "administrator"]  # Add the role names that you consider as admin
    for role in member.roles:
        if role.name.lower() in admin_roles:
            return True
    return False

# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%



def check_existing_path(channel_id):
    paths = get_all_paths()
    for path_id, path_name in paths:
        path_doc = db.collection('paths').document(path_id).get()
        path_data = path_doc.to_dict()
        if channel_id in path_data.get('channels', []):
            return (path_id, path_name)
    return None

def update_user_roles(guild, channel_id):
    channel = guild.get_channel(channel_id)
    if channel:
        for member in channel.members:
            if not member.bot:
                add_path_to_user(member, channel_id)


    # # Update the path document to include the channel
    # db.collection('paths').document(path_id).update({
    #     'channels': firestore.ArrayUnion([str(channel_id)])
    # })



def get_topics_by_path(path_id):
    topics_ref = db.collection('paths').document(path_id).collection('topics').stream()
    topics = [(topic.id, topic.to_dict()) for topic in topics_ref]
    return topics


def add_task(path_id, topic_id, task_name, week):
    task_id = str(uuid.uuid4())

    task_ref = db.collection('tasks').document(task_id)
    task_ref.set({
        'name': task_name,
        'description': '',
        'week': week,
        'path_id': path_id
    })
    
    print(f"Task document created with ID {task_id} and name {task_name}, week {week}")  # Debugging info

    # Update the topic document to include the new task ID
    topic_ref = db.collection('paths').document(path_id).collection('topics').document(topic_id)
    topic_ref.update({
        'tasks': firestore.ArrayUnion([task_id])
    })
    
    print(f"Added task {task_name} with ID {task_id} to topic {topic_id} in path {path_id}")
    return task_id






def mark_user_task(user_id, path_id, task_id, completed, proof_url):
    user_ref = db.collection('users').document(str(user_id))
    task_ref = user_ref.collection('tasks').document(str(task_id))

    task_data = {
        'path_id': path_id,
        'completed': completed,
        'proof_url': proof_url
    }

    task_ref.set(task_data, merge=True)
    print(f"Task {task_id} for user {user_id} marked as completed: {completed}, proof URL: {proof_url}")





# Get

def get_command_usage_by_user(user_id, path_id=None, channel_id=None):
    command_logs_ref = db.collection('command_logs')
    query = command_logs_ref.where('user_id', '==', str(user_id))
    if path_id:
        query = query.where('path_id', '==', path_id)
    if channel_id:
        query = query.where('channel_id', '==', str(channel_id))
    results = query.stream()
    return [doc.to_dict() for doc in results]

def get_command_usage_within_timeframe(start_time, end_time, path_id=None, channel_id=None):
    command_logs_ref = db.collection('command_logs')
    query = command_logs_ref.where('timestamp', '>=', start_time).where('timestamp', '<=', end_time)
    if path_id:
        query = query.where('path_id', '==', path_id)
    if channel_id:
        query = query.where('channel_id', '==', str(channel_id))
    results = query.stream()
    return [doc.to_dict() for doc in results]

def get_command_usage_statistics(path_id=None, channel_id=None):
    command_logs_ref = db.collection('command_logs')
    query = command_logs_ref
    if path_id:
        query = query.where('path_id', '==', path_id)
    if channel_id:
        query = query.where('channel_id', '==', str(channel_id))
    query = query.stream()
    
    user_command_counts = {}
    for doc in query:
        data = doc.to_dict()
        user_id = data['user_id']
        user_command_counts[user_id] = user_command_counts.get(user_id, 0) + 1
    return user_command_counts


def get_function_usage(function_name):
    print(f"Fetching users for function: {function_name}")
    query = db.collection('function_usage').where('function_name', '==', function_name)
    docs = query.stream()
    results = [(doc.id, doc.to_dict()) for doc in docs]
    print(f"Function usage results: {results}")
    return results




# Channel
def get_channel_name(channel_id):
    doc = db.collection('channels').document(channel_id).get()
    if doc.exists:
        return doc.to_dict().get('name')
    return None


def add_user_path(user_id, path_id, channel_id, role):
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        paths = user_data.get('paths', [])
        for path in paths:
            if path['path_id'] == path_id:
                return  # Path already exists for the user
        paths.append({
            'path_id': path_id,
            'channel': {
                'channel_id': channel_id,
                'role': role
            },
            'tasks': []
        })
        user_ref.update({'paths': paths})
    else:
        user_ref.set({
            'name': 'noraec',  # Add other necessary fields here
            'paths': [{
                'path_id': path_id,
                'channel': {
                    'channel_id': channel_id,
                    'role': role
                },
                'tasks': []
            }]
        })



# Function to record satisfaction response in Firestore
def record_satisfaction_response(user_id, responses):
    response_id = str(uuid.uuid4())
    responses["user_id"] = user_id
    db.collection('satisfaction_responses').document(response_id).set(responses)







