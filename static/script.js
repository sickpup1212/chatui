document.addEventListener('DOMContentLoaded', (event) => { 
    var socket = io.connect('http://' + document.domain + ':' + location.port);

    socket.on('status_update', function(data) {
        var statusDiv = document.getElementById('status');
        statusDiv.innerHTML = '';
        var statusMessage = document.createElement('p');
        statusMessage.textContent = 'Status: ' + data.status + ' (ID: ' + data.id + ')';
        statusMessage.classList.add('flash'); 
        while (statusDiv.firstChild) {
            statusDiv.removeChild(statusDiv.firstChild);
        }
        statusDiv.appendChild(statusMessage);

        statusTimeout = setTimeout(() => {
            statusMessage.classList.add('fade-out');
        }, 2500);
    });

    socket.on('chat_message', function(data) {
        if (data.message.match('```') != null) {
            displayResponse(data.message)
        } else {
            var messagesDiv = document.getElementById('messages');
            messagesDiv.innerHTML+=data.message
        }
    });

    socket.on('show_thread', function(data) {
        var tHolder = document.getElementById('threadHolder');
        tHolder.value = data.current_threadID;
        document.getElementById('newThread').style.display = 'block';

    });

});

function fetchOpenAIResponse(message, azzie, gege) {
    fetch('/msg_assistant', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: message, assieID: azzie, thread_dizzle: gege })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Success:', data);
    })
    .catch((error) => {
        console.log('Error:', error);
    });
};

function htmlEncode(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}

function highlighter() {
    var codeElements = [...document.querySelectorAll('#prisme')];
    codeElements.forEach(codeElm => { Prism.highlightElement(codeElm); });
}

function displayResponse(responseText) {
    const container = document.getElementById('messages');
    var splits = responseText.split('```')
    var beforeMessage = splits[0] ? splits[0] : " "
    var afterMessage = splits[2] ? splits[2] : " "
    const codeMatch = responseText.match(/```(\w*)([\s\S]*?)```/);
    if (codeMatch[1] != 'html') {
        const language = codeMatch[1] || 'javascript'; // Default to JavaScript if no language specified
        var content = codeMatch[2];
        var codeElement = `<p>${beforeMessage}</p><pre><code id="prisme" class='language-${language}'>${content}</code></pre><p>${afterMessage}</p>`;
        container.innerHTML += codeElement;
        highlighter();
    } else if (codeMatch[1] == 'html') {
        const htmlContent = htmlEncode(codeMatch[2]);
        var htmlCodeElement = `<p>${beforeMessage}</p><pre><code id="prisme" class='language-html'>${htmlContent}</code></pre><p>${afterMessage}</p>`;
        container.innerHTML += htmlCodeElement;
        highlighter();
    } else {
        container.innerHTML += responseText;
    }
}


