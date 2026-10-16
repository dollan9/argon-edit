// aftereffects_core.jsx - Strict ECMAScript 3 (1999) ExtendScript DOM for After Effects
// Handles MOGRTs, Kinetic Text, Compositions, and ProRes 4444 Alpha Renders.

/**
 * Finds composition by name in project items
 */
function argon_findCompByName(name) {
    if (!app.project) {
        return null;
    }
    for (var i = 1; i <= app.project.numItems; i++) {
        var item = app.project.item(i);
        if (item instanceof CompItem && item.name === name) {
            return item;
        }
    }
    return null;
}

/**
 * Creates or resets a composition
 */
function argon_createComp(compName, width, height, fps, durationSec) {
    try {
        if (!app.project) {
            app.newProject();
        }

        var w = width ? parseInt(width, 10) : 1920;
        var h = height ? parseInt(height, 10) : 1080;
        var f = fps ? parseFloat(fps) : 30.0;
        var d = durationSec ? parseFloat(durationSec) : 5.0;

        var existing = argon_findCompByName(compName);
        if (existing) {
            existing.width = w;
            existing.height = h;
            existing.frameRate = f;
            existing.duration = d;
            return JSON.stringify({
                status: "ok",
                action: "createComp",
                compName: compName,
                compId: existing.id,
                existing: true
            });
        }

        var newComp = app.project.items.addComp(compName, w, h, 1.0, d, f);

        return JSON.stringify({
            status: "ok",
            action: "createComp",
            compName: compName,
            compId: newComp.id,
            existing: false
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "createComp",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Adds a kinetic styled text layer to a composition
 */
function argon_addTextLayer(compName, textContent, fontSize, fontColor, posX, posY, animType) {
    try {
        var comp = argon_findCompByName(compName);
        if (!comp) {
            return JSON.stringify({ status: "error", error: "Composition not found: " + compName });
        }

        var textLayer = comp.layers.addText(textContent || "");
        var sourceText = textLayer.property("Source Text");
        var textDocument = sourceText.value;

        textDocument.fontSize = fontSize ? parseFloat(fontSize) : 72;
        // Color default yellow/gold for punchy retention
        var col = [1.0, 0.85, 0.0];
        if (fontColor && fontColor.length === 3) {
            col = [parseFloat(fontColor[0]), parseFloat(fontColor[1]), parseFloat(fontColor[2])];
        }
        textDocument.fillColor = col;
        textDocument.applyFill = true;
        textDocument.justification = ParagraphJustification.CENTER_JUSTIFY;
        sourceText.setValue(textDocument);

        var pX = posX ? parseFloat(posX) : comp.width / 2;
        var pY = posY ? parseFloat(posY) : comp.height * 0.8;
        if (pX <= 1.0 && pY <= 1.0) {
            pX = pX * comp.width;
            pY = pY * comp.height;
        }

        textLayer.property("Position").setValue([pX, pY]);

        // Kinetic pop-in animation: scale 0 -> 115% -> 100%
        if (animType === "pop" || animType === "kinetic") {
            var scaleProp = textLayer.property("Scale");
            scaleProp.setValueAtTime(0.0, [0, 0]);
            scaleProp.setValueAtTime(0.12, [115, 115]);
            scaleProp.setValueAtTime(0.20, [100, 100]);
        }

        return JSON.stringify({
            status: "ok",
            action: "addTextLayer",
            layerIndex: textLayer.index,
            compName: compName,
            textContent: textContent
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "addTextLayer",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Adds composition to render queue and renders output (e.g. ProRes 4444 with Alpha)
 */
function argon_renderComp(compName, outputPath, outputModule) {
    try {
        var comp = argon_findCompByName(compName);
        if (!comp) {
            return JSON.stringify({ status: "error", error: "Composition not found: " + compName });
        }

        var renderQueue = app.project.renderQueue;
        var renderItem = renderQueue.items.add(comp);
        var om = renderItem.outputModule(1);

        if (outputModule) {
            try {
                om.applyTemplate(outputModule);
            } catch (ignore) {
                // Template not available, keep default
            }
        }

        om.file = new File(outputPath);
        renderQueue.render();

        return JSON.stringify({
            status: "ok",
            action: "renderComp",
            compName: compName,
            outputPath: outputPath
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "renderComp",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Exports composition as a Motion Graphics Template (.mogrt)
 */
function argon_exportMogrt(compName, outputPath) {
    try {
        var comp = argon_findCompByName(compName);
        if (!comp) {
            return JSON.stringify({ status: "error", error: "Composition not found: " + compName });
        }

        var mogrtFile = new File(outputPath);
        if (comp.exportAsMotionGraphicsTemplate) {
            comp.exportAsMotionGraphicsTemplate(false, mogrtFile.fsName);
            return JSON.stringify({
                status: "ok",
                action: "exportMogrt",
                outputPath: outputPath
            });
        }

        return JSON.stringify({
            status: "error",
            error: "exportAsMotionGraphicsTemplate method not supported in this After Effects version."
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "exportMogrt",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}
