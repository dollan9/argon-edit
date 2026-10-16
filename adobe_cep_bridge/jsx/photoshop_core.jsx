// photoshop_core.jsx - Strict ECMAScript 3 (1999) ExtendScript DOM for Photoshop
// Automates high-CTR thumbnail creation, text styles, and image exports.

/**
 * Creates high-CTR YouTube thumbnail composition
 */
function argon_createThumbnail(baseImagePath, headlineText, subtitleText, outputPath, width, height) {
    try {
        var w = width ? parseInt(width, 10) : 1280;
        var h = height ? parseInt(height, 10) : 720;

        var doc;
        var baseFile = new File(baseImagePath);
        if (baseFile.exists) {
            doc = app.open(baseFile);
            doc.resizeImage(UnitValue(w, "px"), UnitValue(h, "px"), 72, ResampleMethod.BICUBIC);
        } else {
            doc = app.documents.add(UnitValue(w, "px"), UnitValue(h, "px"), 72, "ArgonThumbnail", NewDocumentMode.RGB);
        }

        // Headline Text Layer
        if (headlineText) {
            var headLayer = doc.artLayers.add();
            headLayer.kind = LayerKind.TEXT;
            var headItem = headLayer.textItem;
            headItem.contents = String(headlineText).toUpperCase();
            headItem.size = UnitValue(68, "pt");
            headItem.position = [UnitValue(w * 0.08, "px"), UnitValue(h * 0.35, "px")];

            var headColor = new SolidColor();
            headColor.rgb.red = 255;
            headColor.rgb.green = 220;
            headColor.rgb.blue = 0;
            headItem.color = headColor;
        }

        // Subtitle Text Layer
        if (subtitleText) {
            var subLayer = doc.artLayers.add();
            subLayer.kind = LayerKind.TEXT;
            var subItem = subLayer.textItem;
            subItem.contents = String(subtitleText);
            subItem.size = UnitValue(36, "pt");
            subItem.position = [UnitValue(w * 0.08, "px"), UnitValue(h * 0.50, "px")];

            var subColor = new SolidColor();
            subColor.rgb.red = 255;
            subColor.rgb.green = 255;
            subColor.rgb.blue = 255;
            subItem.color = subColor;
        }

        // Save PSD and PNG
        var outF = new File(outputPath);
        if (outF.parent && !outF.parent.exists) {
            outF.parent.create();
        }

        var pngSaveOptions = new PNGSaveOptions();
        pngSaveOptions.compression = 6;
        pngSaveOptions.interlaced = false;
        doc.saveAs(outF, pngSaveOptions, true, Extension.LOWERCASE);

        return JSON.stringify({
            status: "ok",
            action: "createThumbnail",
            outputPath: outputPath,
            width: w,
            height: h
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "createThumbnail",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Adds high-contrast callout badge
 */
function argon_addBadge(text, badgeColor, posX, posY) {
    try {
        if (!app.documents.length) {
            return JSON.stringify({ status: "error", error: "No active document in Photoshop." });
        }
        var doc = app.activeDocument;
        var badgeLayer = doc.artLayers.add();
        badgeLayer.kind = LayerKind.TEXT;
        var textItem = badgeLayer.textItem;
        textItem.contents = String(text);
        textItem.size = UnitValue(28, "pt");

        var col = new SolidColor();
        if (badgeColor && badgeColor.length === 3) {
            col.rgb.red = parseInt(badgeColor[0], 10);
            col.rgb.green = parseInt(badgeColor[1], 10);
            col.rgb.blue = parseInt(badgeColor[2], 10);
        } else {
            col.rgb.red = 255;
            col.rgb.green = 50;
            col.rgb.blue = 50;
        }
        textItem.color = col;

        var pX = posX ? parseFloat(posX) : doc.width.as("px") * 0.7;
        var pY = posY ? parseFloat(posY) : doc.height.as("px") * 0.2;
        textItem.position = [UnitValue(pX, "px"), UnitValue(pY, "px")];

        return JSON.stringify({
            status: "ok",
            action: "addBadge",
            text: text,
            posX: pX,
            posY: pY
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "addBadge",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Export active Photoshop document to PNG
 */
function argon_exportPNG(outputPath) {
    try {
        if (!app.documents.length) {
            return JSON.stringify({ status: "error", error: "No active document in Photoshop." });
        }
        var doc = app.activeDocument;
        var outF = new File(outputPath);
        if (outF.parent && !outF.parent.exists) {
            outF.parent.create();
        }

        var pngSaveOptions = new PNGSaveOptions();
        pngSaveOptions.compression = 4;
        pngSaveOptions.interlaced = false;
        doc.saveAs(outF, pngSaveOptions, true, Extension.LOWERCASE);

        return JSON.stringify({
            status: "ok",
            action: "exportPNG",
            outputPath: outputPath
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "exportPNG",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}
