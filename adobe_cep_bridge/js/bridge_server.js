/**
 * bridge_server.js
 * Runs inside the Adobe CEP Node.js context.
 * Binds an HTTP server to port 8088 (PPRO), 8089 (AEFT), or 8090 (PHXS).
 * Listens for incoming JSX execution requests, passes them to csInterface.evalScript(),
 * and returns the output as structured JSON.
 */

(function () {
    "use strict";

    // Ensure Node.js environment is available
    if (typeof require === "undefined") {
        console.error("[ArgonBridge] Node.js is not enabled in this CEP extension manifest!");
        updateUIStatus(false, "Node.js disabled", "N/A", "Disabled");
        return;
    }

    var http = require("http");
    var fs = require("fs");
    var path = require("path");

    var csInterface = new CSInterface();
    var hostEnv = csInterface.getHostEnvironment();
    var appId = (hostEnv && hostEnv.appId) ? hostEnv.appId.toUpperCase() : "PPRO";

    // Port mapping by host application
    var portMap = {
        "PPRO": 8088,
        "AEFT": 8089,
        "PHXS": 8090,
        "AUDT": 8084
    };

    var serverPort = portMap[appId] || 8088;

    function logMsg(msg) {
        var timestamp = new Date().toISOString().split("T")[1].replace("Z", "");
        var line = "[" + timestamp + "] " + msg;
        console.log("[ArgonBridge] " + line);
        var logBox = document.getElementById("logBox");
        if (logBox) {
            logBox.textContent = line + "\n" + logBox.textContent.slice(0, 5000);
        }
    }

    function updateUIStatus(isOnline, statusTxt, appName, port) {
        var statusDot = document.getElementById("statusDot");
        var statusText = document.getElementById("statusText");
        var hostApp = document.getElementById("hostApp");
        var portDisplay = document.getElementById("portDisplay");
        var nodeStatus = document.getElementById("nodeStatus");

        if (statusDot) statusDot.style.backgroundColor = isOnline ? "#28a745" : "#dc3545";
        if (statusText) statusText.textContent = statusTxt;
        if (hostApp) hostApp.textContent = appName;
        if (portDisplay) portDisplay.textContent = port;
        if (nodeStatus) nodeStatus.textContent = typeof process !== "undefined" ? process.version : "Enabled";
    }

    /**
     * Preload json2 polyfill and core jsx files into ExtendScript context
     */
    function loadCoreJSX() {
        try {
            var extensionRoot = csInterface.getSystemPath("extension");
            var json2Path = path.join(extensionRoot, "jsx", "json2.jsx");
            if (fs.existsSync(json2Path)) {
                var json2Code = fs.readFileSync(json2Path, "utf8");
                csInterface.evalScript(json2Code, function () {
                    logMsg("json2.jsx polyfill loaded into ExtendScript context.");
                });
            }

            var coreFileMap = {
                "PPRO": "premiere_core.jsx",
                "AEFT": "aftereffects_core.jsx",
                "PHXS": "photoshop_core.jsx"
            };

            var specificCore = coreFileMap[appId] || "premiere_core.jsx";
            var corePath = path.join(extensionRoot, "jsx", specificCore);
            if (fs.existsSync(corePath)) {
                var coreCode = fs.readFileSync(corePath, "utf8");
                csInterface.evalScript(coreCode, function (res) {
                    logMsg(specificCore + " loaded into ExtendScript context.");
                });
            }
        } catch (err) {
            logMsg("Error preloading JSX files: " + err.message);
        }
    }

    // Set CORS and headers
    function sendJSON(res, statusCode, payload) {
        res.writeHead(statusCode, {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        });
        res.end(JSON.stringify(payload));
    }

    var server = http.createServer(function (req, res) {
        // Handle CORS preflight
        if (req.method === "OPTIONS") {
            res.writeHead(204, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            });
            res.end();
            return;
        }

        // Health check endpoint
        if (req.method === "GET" && (req.url === "/health" || req.url === "/")) {
            sendJSON(res, 200, {
                status: "ok",
                appId: appId,
                port: serverPort,
                node_version: process.version,
                uptime_sec: process.uptime()
            });
            return;
        }

        // Execute JSX endpoint
        if (req.method === "POST" && (req.url === "/execute_jsx" || req.url === "/eval")) {
            var bodyChunks = [];
            req.on("data", function (chunk) {
                bodyChunks.push(chunk);
            });

            req.on("end", function () {
                var bodyStr = Buffer.concat(bodyChunks).toString("utf8");
                var parsed;
                try {
                    parsed = JSON.parse(bodyStr);
                } catch (e) {
                    sendJSON(res, 400, {
                        status: "error",
                        error_trace: "Malformed JSON payload: " + e.message
                    });
                    return;
                }

                var scriptToExecute = "";

                if (parsed.function_name) {
                    var args = parsed.args || [];
                    var serializedArgs = "";
                    if (Array.isArray(args)) {
                        serializedArgs = args.map(function (arg) {
                            return JSON.stringify(arg);
                        }).join(", ");
                    } else if (typeof args === "object") {
                        serializedArgs = JSON.stringify(args);
                    }
                    scriptToExecute = parsed.function_name + "(" + serializedArgs + ");";
                } else if (parsed.script) {
                    scriptToExecute = parsed.script;
                } else {
                    sendJSON(res, 400, {
                        status: "error",
                        error_trace: "Payload must provide either 'script' or 'function_name'."
                    });
                    return;
                }

                logMsg("Executing JSX: " + scriptToExecute.slice(0, 120) + (scriptToExecute.length > 120 ? "..." : ""));

                // Wrap in ES3 try-catch inside ExtendScript to catch ExtendScript runtime errors
                var wrappedScript = "(function() { try { var __res = " + scriptToExecute + "; return (typeof __res === 'string') ? __res : ((typeof JSON !== 'undefined' && JSON.stringify) ? JSON.stringify(__res) : String(__res)); } catch(err) { return 'ARGON_ERROR: ' + (err.message || String(err)) + (err.line ? (' at line ' + err.line) : ''); } })();";

                csInterface.evalScript(wrappedScript, function (result) {
                    if (typeof result === "string" && result.indexOf("ARGON_ERROR:") === 0) {
                        logMsg("JSX Error: " + result);
                        sendJSON(res, 500, {
                            status: "error",
                            error_trace: result.replace("ARGON_ERROR: ", "")
                        });
                        return;
                    }

                    var parsedResult = result;
                    try {
                        parsedResult = JSON.parse(result);
                    } catch (ignore) {
                        // Keep as string if not valid JSON
                    }

                    logMsg("JSX Success returned.");
                    sendJSON(res, 200, {
                        status: "ok",
                        result: parsedResult
                    });
                });
            });
            return;
        }

        // Unknown endpoint
        sendJSON(res, 404, {
            status: "error",
            error_trace: "Endpoint not found: " + req.method + " " + req.url
        });
    });

    server.on("error", function (err) {
        logMsg("Server error: " + err.message);
        updateUIStatus(false, "Server Error: " + err.code, appId, serverPort);
    });

    server.listen(serverPort, "127.0.0.1", function () {
        logMsg("Argon CEP Bridge HTTP Server listening on http://127.0.0.1:" + serverPort);
        updateUIStatus(true, "Online (Listening)", appId, serverPort);
        loadCoreJSX();
    });

})();
