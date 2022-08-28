// Chat script


(function (e) {
    console.log("echo")

    const win_loc = window.location
    const host = win_loc.host
    const href = win_loc.href

    const url = new URL(href)
    const room_id = url.searchParams.get('room') || ''

    if (room_id == '') {
        throw new Error(`http://${host}?room=<room_id>`)
    }

    const ws_url = `ws://${host}/chat/${room_id}`

    const ws = new WebSocket(ws_url)

    ws.onopen = function (e) {
        console.log("OPEN", e)
    }

    ws.onerror = function (e) {
        console.log("ERROR", e)
    }

    ws.onclose = function (e) {
        console.log("CLOSE", e)
    }

    ws.onmessage = function (e) {
        console.log("MESSAGE", e)
        if (JSON.parse(e.data).code == 404) {
            alert(JSON.parse(e.data).message)
            window.location = `http://${host}`
        }

    }

    function send_message(message = "", data = {}) {
        ws.send(JSON.stringify({
            "message": message,
            "ts": new Date().toISOString()
        }))
    };

    // test
    btn = document.getElementById('btn')
    btn.onclick = function () {
        console.log('click')
        send_message(message = Math.random())
    }

    active_room_a_tag = document.getElementById(`room_${room_id}`)
    active_room_a_tag.classList.add('active')
    active_room_a_tag.ariaCurrent = true
})();