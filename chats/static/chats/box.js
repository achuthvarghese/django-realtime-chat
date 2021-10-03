(function (e) {
    const win_loc = window.location
    const host = win_loc.host
    const href = win_loc.href

    const url = new URL(href)
    const chat_with = url.searchParams.get('with')

    const ws_url = `ws://${host}/chat/${chat_with}`

    const ws = new ReconnectingWebSocket(ws_url)

    ws.onopen = function (e) {
        console.log("OPEN", e)
        // ws_send({ "message": "Hello from client" })
    }

    ws.onerror = function (e) {
        console.log("ERROR", e)
    }

    ws.onclose = function (e) {
        console.log("CLOSE", e)
    }

    ws.onmessage = function (e) {
        data = JSON.parse(e.data)
        msg = data["message"]
        // author = data["author"]
        
        create_p_and_scroll(msg)
    }

    input_msg = document.getElementById("msg")
    btn_send = document.getElementById("send")
    div_msgs = document.getElementById("msgs")

    input_msg.addEventListener("keyup", function (event) {
        if (event.keyCode == 13) {
            btn_send.click()
        }
    })

    btn_send.onclick = function () {
        msg = input_msg.value
        if (msg != "") {
            ws_send({ "message": msg })
            // create_p_and_scroll(msg)
            input_msg.value = ""
            input_msg.autofocus
        }
    }

    function ws_send(data) {
        ws.send(JSON.stringify(data))
    }

    function create_p_and_scroll(msg, text_align = "right") {
        msg_node = document.createElement("p")
        msg_node.style.textAlign = text_align
        msg_node.textContent = msg
        msg_node.className = `msg msg-align-${text_align}`

        div_msgs.appendChild(msg_node)
        div_msgs.scrollTop = div_msgs.scrollHeight
    }
})();