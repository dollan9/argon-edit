/**
 * bridge_server.js
 * Runs inside the Adobe CEP Node.js context.
 * Binds an HTTP server to port 8088 (PPRO), 8089 (AEFT), or 8090 (PHXS).
 * Listens for incoming JSX execution requests, passes them to csInterface.evalScript(),
 * and returns the output as structured JSON.
 *
 * PRODUCTION-HARDENED:
 * Implements a strict Single-Threaded FIFO Queue Manager with mandatory 50ms execution buffer
 * to prevent ExtendScript concurrency deadlocks and drops in Premiere Pro.
 * Limits queue depth to 50 with HTTP 429 backpressure.
 */

(function () {
    "use strict";

    // Ensure Node.js environment is available
    if (typeof require === "undefined") {
        console.error("[ArgonBridge] Node.js is not enabled in this CEP extension manifest!");
        updateUIStatus(false, "Node.js disabled", "N/A", "Disabled", 0);
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

    // -------------------------------------------------------------------------
    // FIFO Queue State & Constants
    // -------------------------------------------------------------------------
    var MAX_QUEUE_DEPTH = 50;
    var EXECUTION_BUFFER_MS = 50;
    var taskQueue = [];
    var isProcessingQueue = false;

    function logMsg(msg) {
        var timestamp = new Date().toISOString().split("T")[1].replace("Z", "");
        var line = "[" + timestamp + "] " + msg;
        console.log("[ArgonBridge] " + line);
        var logBox = document.getElementById("logBox");
        if (logBox) {
            logBox.textContent = line + "\n" + logBox.textContent.slice(0, 5000);
        }
    }

    function updateUIStatus(isOnline, statusTxt, appName, port, queueDepth) {
        var statusDot = document.getElementById("statusDot");
        var statusText = document.getElementById("statusText");
        var hostApp = document.getElementById("hostApp");
        var portDisplay = document.getElementById("portDisplay");
        var nodeStatus = document.getElementById("nodeStatus");
        var queueDisplay = document.getElementById("queueDisplay");

        if (statusDot) statusDot.style.backgroundColor = isOnline ? "#28a745" : "#dc3545";
        if (statusText) statusText.textContent = statusTxt;
        if (hostApp) hostApp.textContent = appName;
        if (portDisplay) portDisplay.textContent = port;
        if (nodeStatus) nodeStatus.textContent = typeof process !== "undefined" ? process.version : "Enabled";
        if (queueDisplay) queueDisplay.textContent = String(queueDepth || taskQueue.length);
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
                csInterface.evalScript(coreCode, function () {
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
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "X-Argon-Queue-Depth": String(taskQueue.length)
        });
        res.end(JSON.stringify(payload));
    }

    // -------------------------------------------------------------------------
    // Single-Threaded FIFO Queue Processor
    // -------------------------------------------------------------------------
    function processNextTask() {
        if (isProcessingQueue) {
            return;
        }

        if (taskQueue.length === 0) {
            updateUIStatus(true, "Idle (Listening)", appId, serverPort, 0);
            return;
        }

        isProcessingQueue = true;
        var task = taskQueue.shift();
        updateUIStatus(true, "Executing JSX (" + taskQueue.length + " queued)", appId, serverPort, taskQueue.length);

        var scriptToExecute = task.script;
        var res = task.res;
        var taskId = task.id;

        logMsg("[Queue Task #" + taskId + "] Executing (" + taskQueue.length + " remaining in queue)...");

        // Wrap in ES3 try-catch inside ExtendScript using eval() to safely handle declarations and multi-line scripts
        var wrappedScript = "(function() { try { var __res = eval(" + JSON.stringify(scriptToExecute) + "); return (typeof __res === 'string') ? __res : ((typeof JSON !== 'undefined' && JSON.stringify) ? JSON.stringify(__res) : String(__res)); } catch(err) { return 'ARGON_ERROR: ' + (err.message || String(err)) + (err.line ? (' at line ' + err.line) : ''); } })();";

        try {
            csInterface.evalScript(wrappedScript, function (result) {
                try {
                    if (typeof result === "string" && result.indexOf("ARGON_ERROR:") === 0) {
                        var errTrace = result.replace("ARGON_ERROR: ", "");
                        logMsg("[Queue Task #" + taskId + "] JSX Error: " + errTrace);
                        sendJSON(res, 500, {
                            status: "error",
                            task_id: taskId,
                            error_trace: errTrace,
                            queue_depth: taskQueue.length
                        });
                    } else {
                        var parsedResult = result;
                        try {
                            parsedResult = JSON.parse(result);
                        } catch (ignore) {
                            // Keep as raw string if not JSON
                        }

                        logMsg("[Queue Task #" + taskId + "] Success returned.");
                        sendJSON(res, 200, {
                            status: "ok",
                            task_id: taskId,
                            result: parsedResult,
                            queue_depth: taskQueue.length
                        });
                    }
                } catch (sendErr) {
                    logMsg("[Queue Task #" + taskId + "] Response send error: " + sendErr.message);
                } finally {
                    // Mandatory 50ms buffer before releasing lock and processing next queued task
                    setTimeout(function () {
                        isProcessingQueue = false;
                        processNextTask();
                    }, EXECUTION_BUFFER_MS);
                }
            });
        } catch (dispatchErr) {
            logMsg("[Queue Task #" + taskId + "] csInterface dispatch error: " + dispatchErr.message);
            sendJSON(res, 500, {
                status: "error",
                task_id: taskId,
                error_trace: "Dispatch failed: " + dispatchErr.message,
                queue_depth: taskQueue.length
            });
            setTimeout(function () {
                isProcessingQueue = false;
                processNextTask();
            }, EXECUTION_BUFFER_MS);
        }
    }

    var taskIdCounter = 1;

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
                uptime_sec: process.uptime(),
                queue_depth: taskQueue.length,
                is_busy: isProcessingQueue
            });
            return;
        }

        // Execute JSX endpoint
        if (req.method === "POST" && (req.url === "/execute_jsx" || req.url === "/eval")) {
            // Check queue depth limit (Backpressure HTTP 429)
            if (taskQueue.length >= MAX_QUEUE_DEPTH) {
                logMsg("WARNING: Queue full (" + taskQueue.length + "/" + MAX_QUEUE_DEPTH + "). Returning HTTP 429.");
                sendJSON(res, 429, {
                    status: "error",
                    error_trace: "Queue depth exceeded maximum limit (" + MAX_QUEUE_DEPTH + " tasks). ExtendScript engine is busy.",
                    queue_depth: taskQueue.length
                });
                return;
            }

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
                        error_trace: "Malformed JSON payload: " + e.message,
                        queue_depth: taskQueue.length
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
                        error_trace: "Payload must provide either 'script' or 'function_name'.",
                        queue_depth: taskQueue.length
                    });
                    return;
                }

                var taskId = taskIdCounter++;
                logMsg("Enqueued Task #" + taskId + " (Queue depth: " + (taskQueue.length + 1) + ")");

                // Push task to FIFO queue
                taskQueue.push({
                    id: taskId,
                    script: scriptToExecute,
                    res: res,
                    enqueuedAt: Date.now()
                });

                // Trigger processing loop
                processNextTask();
            });
            return;
        }

        // Unknown endpoint
        sendJSON(res, 404, {
            status: "error",
            error_trace: "Endpoint not found: " + req.method + " " + req.url,
            queue_depth: taskQueue.length
        });
    });

    server.on("error", function (err) {
        logMsg("Server error: " + err.message);
        updateUIStatus(false, "Server Error: " + err.code, appId, serverPort, taskQueue.length);
    });

    server.listen(serverPort, "127.0.0.1", function () {
        logMsg("Argon CEP Bridge HTTP Server listening on http://127.0.0.1:" + serverPort);
        updateUIStatus(true, "Online (Listening)", appId, serverPort, 0);
        loadCoreJSX();
    });

})();
