// ==UserScript==
// @name             Colonist interceptor
// @include          /^https://colonist.io/
// @run-at           document-start
// @grant            none
// ==/UserScript==

const colonistioActions = Object.freeze({
    THROW_DICE: "15",
    PASS_TURN: "19",
    BUY_DEVELOPMENT_CARD: "26",
    BUILD_ROAD: "23",
    BUILD_SETTLEMENT: "26",
    BUILD_CITY: "28"
})

const EncoderModule = (function () {
    let instance
    /* eslint-disable */
    function createInstance () {
        const e = window.webpackJsonp[0][1] // Modules used by colonist.io are hidden here
        const i = {}
        function o (t) {
            if (i[t]) { return i[t].exports }
            const a = i[t] = {
                i: t,
                l: !1,
                exports: {}
            }
            return e[t].call(a.exports, a, a.exports, o),
            a.l = !0,
            a.exports
        }
        o.m = e,
        o.c = i,
        o.d = function (e, t, a) {
            o.o(e, t) || Object.defineProperty(e, t, {
                enumerable: !0,
                get: a
            })
        }
        ,
        o.r = function (e) {
            typeof Symbol !== "undefined" && Symbol.toStringTag && Object.defineProperty(e, Symbol.toStringTag, {
                value: "Module"
            }),
            Object.defineProperty(e, "__esModule", {
                value: !0
            })
        }
        ,
        o.t = function (e, t) {
            if (1 & t && (e = o(e)),
            8 & t) { return e }
            if (4 & t && typeof e === "object" && e && e.__esModule) { return e }
            const a = Object.create(null)
            if (o.r(a),
            Object.defineProperty(a, "default", {
                enumerable: !0,
                value: e
            }),
            2 & t && typeof e !== "string") {
                for (const i in e) {
                    o.d(a, i, function (t) {
                        return e[t]
                    }
                        .bind(null, i))
                }
            }
            return a
        }
        ,
        o.n = function (e) {
            const t = e && e.__esModule
                ? function () {
                    return e.default
                }
                : function () {
                    return e
                }

            return o.d(t, "a", t),
            t
        }
        ,
        o.o = function (e, t) {
            return Object.prototype.hasOwnProperty.call(e, t)
        }
        ,
        o.p = "/dist"

        return o(540) // The module we need is located in window.webpackJsonp[0][1]
    }
    /* eslint-enable */

    return {
        getInstance: function () {
            if (!instance) {
                instance = createInstance()
            }
            return instance
        }
    }
})()

const botSocket = new WebSocket("ws://localhost:8765")
let gameSocket
const NativeWebSocket = window.WebSocket
window.WebSocket = function (...args) {
    const socket = new NativeWebSocket(...args)
    socket.addEventListener("message", function (event) {
        const msg = event.data
        let data = EncoderModule.getInstance().decode(msg).data
        if (typeof data === "object") data = JSON.stringify(data)
        botSocket.send(data)
    })
    const nativeSend = socket.send
    socket.send = function (data) {
        const decodedData = EncoderModule.getInstance().decode(data)
        console.log(decodedData)
        nativeSend.apply(this, [data])
    }
    gameSocket = socket
    return socket
}

botSocket.onmessage = function (event) {
    const parsedData = JSON.parse(event.data)

    let gameSocketData
    switch (parsedData.action) {
    case 0: // Build road
        gameSocketData = { id: colonistioActions.BUILD_ROAD, data: parsedData.data } // data: road id
        break
    case 1: // Build settlement
        gameSocketData = { id: colonistioActions.BUILD_SETTLEMENT, data: parsedData.data } // data: settlement id
        break
    case 2: // Build city
        gameSocketData = { id: colonistioActions.BUILD_CITY, data: parsedData.data } // data: settlement id
        break
    case 3: // Buy development card
        gameSocketData = { id: colonistioActions.BUY_DEVELOPMENT_CARD, data: true }
        break
    case 4: // Throw dice
        gameSocketData = { id: colonistioActions.THROW_DICE, data: true }
        break
    case 5: // Pass turn
        gameSocketData = { id: colonistioActions.PASS_TURN, data: true }
        break
    default:
        return
    }

    const encodedData = EncoderModule.getInstance().encode(gameSocketData)
    gameSocket.send(encodedData)
}
