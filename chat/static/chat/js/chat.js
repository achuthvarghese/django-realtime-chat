// Chat script


(function (e) {

    const user = JSON.parse(document.getElementById('user').textContent);

    const win_loc = window.location
    const host = win_loc.host
    const href = win_loc.href

    const url = new URL(href)
    const room_id = url.searchParams.get('room') || ''

    searchUserGroup()

    if (room_id == '') {
        return
        // throw new Error(`http://${host}?room=<room_id>`)
    }

    const ws_url = `ws://${host}/chat/${room_id}`

    const ws = new WebSocket(ws_url)

    // Handle WebSocket on opening a connection
    ws.onopen = function (e) {
        console.log("WS Open")
    }

    // Handle WebSocket on occurance of error
    ws.onerror = function (e) {
        console.log("WS Error")
    }

    // Handle WebSocket connection while closeing
    ws.onclose = function (e) {
        console.log("WS Close")
    }

    // Handle when message is received on WebSocket
    ws.onmessage = function (e) {
        if (JSON.parse(e.data).code == 404) {
            alert(JSON.parse(e.data).message)
            window.location = `http://${host}`
        }

        data = JSON.parse(e.data)
        msgNode = document.createElement("div")
        if (user == data.user) {
            messageSide = 'right'
        } else {
            messageSide = 'left'
        }
        parseDate = moment(data.created_at)
        dateCreated = parseDate.format('MMM D, YYYY, h:mm A')
        msgNode.className = `message message-${messageSide} border rounded mb-1 p-1`
        msgNode.innerHTML = `${data.message} <br><span class="text-muted fw-lighter">by ${data.user} on ${dateCreated}</span>`

        mb = document.getElementById('messages')
        mb.appendChild(msgNode)

        scrollToLatest()

    }

    // Function to send messages on WebSocket
    function send_message(message = "", data = {}) {
        ws.send(JSON.stringify({
            "message": message,
            "ts": new Date().toISOString()
        }))
    };


    // Send message
    btn = document.getElementById('btn')
    btn.onclick = function () {
        messageInput = document.getElementById("message")
        textContent = messageInput.value

        if (textContent != '') {
            messageInput.classList.remove('border-danger')
            send_message(message = textContent)
            messageInput.value = ""
        } else {
            messageInput.classList.add('border-danger')
        }
    }


    // Set active class to current chat head
    active_room_a_tag = document.getElementById(`room_${room_id}`)
    active_room_a_tag.classList.add('active')
    active_room_a_tag.ariaCurrent = true


    // Scroll to the latest message
    function scrollToLatest() {
        mb = document.getElementById('messages')
        mb.scrollTop = mb.scrollHeight
    }

    scrollToLatest()


    // Convert datetime to locale datetime
    span_dates = document.getElementsByClassName('date')
    for (let span_date = 0; span_date < span_dates.length; span_date++) {
        element = span_dates[span_date];
        parseDate = moment(element.dataset.date)
        dateCreated = parseDate.format('MMM D, YYYY, h:mm A')
        element.textContent = dateCreated
    }

    // Search and list for chat user/group name
    function searchUserGroup() {        
        search_input = document.getElementById("search-room-input");
        search_button = document.getElementById("search-room-btn");

        search_input.onsearch = search_button.onclick = () => {
            search_string = search_input.value.trim()
            rooms = document.getElementsByClassName('room')

            for (let room = 0; room < rooms.length; room++) {
                element = rooms[room];
                string_check = element.textContent.trim().toLowerCase().includes(search_string)
                if (string_check) {
                    element.style.display = 'block';
                } else {
                    element.style.display = 'none';    
                }
            }
        }
    }

})();