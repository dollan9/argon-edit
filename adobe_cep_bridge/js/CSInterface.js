/**
 * CSInterface - v11.0.0
 * Standard Adobe CEP interface wrapper for communication between HTML5/NodeJS panel and ExtendScript DOM.
 */
(function () {
    "use strict";

    function CSInterface() {}

    CSInterface.prototype.hostEnvironment = null;

    CSInterface.prototype.getHostEnvironment = function () {
        if (!this.hostEnvironment) {
            var hostEnv = window.__adobe_cep__ ? window.__adobe_cep__.getHostEnvironment() : null;
            if (hostEnv) {
                this.hostEnvironment = JSON.parse(hostEnv);
            } else {
                this.hostEnvironment = {
                    appName: "PPRO",
                    appVersion: "24.0.0",
                    appLocale: "en_US",
                    appUILocale: "en_US",
                    appId: "PPRO"
                };
            }
        }
        return this.hostEnvironment;
    };

    /**
     * Evaluates an ExtendScript expression in the host application.
     * @param {string} script The ExtendScript string to evaluate.
     * @param {function} callback Optional callback receiving the string result.
     */
    CSInterface.prototype.evalScript = function (script, callback) {
        if (!callback) {
            callback = function () {};
        }
        if (window.__adobe_cep__) {
            window.__adobe_cep__.evalScript(script, callback);
        } else {
            console.warn("[CSInterface Mock] evalScript called outside CEP environment:", script);
            callback("MOCK_RESULT_OK");
        }
    };

    CSInterface.prototype.closeExtension = function () {
        if (window.__adobe_cep__) {
            window.__adobe_cep__.closeExtension();
        } else {
            window.close();
        }
    };

    CSInterface.prototype.getSystemPath = function (pathType) {
        if (window.__adobe_cep__) {
            var path = window.__adobe_cep__.getSystemPath(pathType);
            return path ? decodeURI(path) : "";
        }
        return "";
    };

    CSInterface.prototype.addEventListener = function (type, listener, obj) {
        if (window.__adobe_cep__) {
            window.__adobe_cep__.addEventListener(type, listener, obj);
        }
    };

    CSInterface.prototype.removeEventListener = function (type, listener, obj) {
        if (window.__adobe_cep__) {
            window.__adobe_cep__.removeEventListener(type, listener, obj);
        }
    };

    CSInterface.prototype.dispatchEvent = function (event) {
        if (window.__adobe_cep__) {
            window.__adobe_cep__.dispatchEvent(event);
        }
    };

    window.CSInterface = CSInterface;
})();
