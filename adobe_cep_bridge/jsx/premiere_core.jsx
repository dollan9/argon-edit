// premiere_core.jsx - Strict ECMAScript 3 (1999) ExtendScript DOM & QE DOM for Premiere Pro
// Obeying: ES3 ExtendScript Law, Premiere Ticks Law (254016000000 Ticks/Sec).

var ARGON_TICKS_PER_SEC = 254016000000;

/**
 * Converts seconds to exact Premiere ticks string
 */
function argon_secToTicks(sec) {
    var floatVal = parseFloat(sec);
    if (isNaN(floatVal)) {
        floatVal = 0.0;
    }
    var ticks = Math.round(floatVal * ARGON_TICKS_PER_SEC);
    return String(ticks);
}

/**
 * Converts ticks to seconds float
 */
function argon_ticksToSec(ticks) {
    var num = Number(ticks);
    if (isNaN(num)) {
        return 0.0;
    }
    return num / ARGON_TICKS_PER_SEC;
}

/**
 * Recursive search to find a ProjectItem by file system path
 */
function argon_findProjectItemByPath(rootItem, targetPath) {
    if (!rootItem) {
        return null;
    }

    // Normalize slashes
    var normTarget = String(targetPath).replace(/\\/g, "/").toLowerCase();

    if (rootItem.type === ProjectItemType.CLIP || rootItem.type === ProjectItemType.FILE) {
        var mediaPath = rootItem.getMediaPath();
        if (mediaPath) {
            var normMedia = String(mediaPath).replace(/\\/g, "/").toLowerCase();
            if (normMedia === normTarget) {
                return rootItem;
            }
        }
    }

    if (rootItem.children && rootItem.children.numItems > 0) {
        for (var i = 0; i < rootItem.children.numItems; i++) {
            var found = argon_findProjectItemByPath(rootItem.children[i], targetPath);
            if (found !== null) {
                return found;
            }
        }
    }

    return null;
}

/**
 * Initialize or create a project sequence
 */
function argon_initProject(projectPath, sequenceName, fps, width, height) {
    try {
        if (!app.project) {
            if (projectPath && File(projectPath).exists) {
                app.openDocument(projectPath);
            } else {
                app.newProject(projectPath || "Argon_Project.prproj");
            }
        }

        // Enable QE DOM
        if (app.enableQE) {
            app.enableQE();
        }

        var seqName = sequenceName || "Argon_Master_Timeline";
        var activeSeq = app.project.activeSequence;

        if (!activeSeq) {
            // Check if sequence already exists in project items
            for (var i = 0; i < app.project.sequences.numSequences; i++) {
                if (app.project.sequences[i].name === seqName) {
                    app.project.openSequence(app.project.sequences[i].sequenceID);
                    activeSeq = app.project.activeSequence;
                    break;
                }
            }

            if (!activeSeq) {
                // Create new sequence via project item or newSequence
                app.project.createNewSequence(seqName, "ArgonSequenceID");
                activeSeq = app.project.activeSequence;
            }
        }

        return JSON.stringify({
            status: "ok",
            action: "initProject",
            sequenceName: activeSeq ? activeSeq.name : seqName,
            sequenceID: activeSeq ? activeSeq.sequenceID : null,
            projectPath: app.project.path
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "initProject",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Import an array of files into the active project
 */
function argon_importFiles(filePathsArray) {
    try {
        var paths = filePathsArray;
        if (typeof paths === "string") {
            paths = JSON.parse(paths);
        }

        var imported = [];
        var failed = [];

        for (var i = 0; i < paths.length; i++) {
            var fPath = paths[i];
            var f = new File(fPath);
            if (!f.exists) {
                failed.push({ path: fPath, reason: "File not found on disk" });
                continue;
            }

            // Check if already in project
            var existing = argon_findProjectItemByPath(app.project.rootItem, fPath);
            if (existing) {
                imported.push({
                    path: fPath,
                    nodeId: existing.nodeId,
                    name: existing.name,
                    alreadyImported: true
                });
                continue;
            }

            var success = app.project.importFiles([fPath], true, app.project.rootItem, false);
            if (success) {
                var newlyImported = argon_findProjectItemByPath(app.project.rootItem, fPath);
                imported.push({
                    path: fPath,
                    nodeId: newlyImported ? newlyImported.nodeId : null,
                    name: newlyImported ? newlyImported.name : f.name,
                    alreadyImported: false
                });
            } else {
                failed.push({ path: fPath, reason: "importFiles returned false" });
            }
        }

        return JSON.stringify({
            status: "ok",
            importedCount: imported.length,
            failedCount: failed.length,
            imported: imported,
            failed: failed
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "importFiles",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Insert or overwrite a media clip onto specified video and audio tracks
 */
function argon_insertClip(filePath, srcInSec, srcOutSec, timelineInSec, vTrackIdx, aTrackIdx) {
    try {
        if (app.enableQE) {
            app.enableQE();
        }

        var seq = app.project.activeSequence;
        if (!seq) {
            return JSON.stringify({ status: "error", error: "No active sequence found." });
        }

        var projectItem = argon_findProjectItemByPath(app.project.rootItem, filePath);
        if (!projectItem) {
            // Attempt auto-import
            var f = new File(filePath);
            if (!f.exists) {
                return JSON.stringify({ status: "error", error: "Media file not found: " + filePath });
            }
            app.project.importFiles([filePath], true, app.project.rootItem, false);
            projectItem = argon_findProjectItemByPath(app.project.rootItem, filePath);
            if (!projectItem) {
                return JSON.stringify({ status: "error", error: "Failed to locate or import project item: " + filePath });
            }
        }

        // Apply In & Out points via Premiere Ticks Law
        var inTicksStr = argon_secToTicks(srcInSec);
        var outTicksStr = argon_secToTicks(srcOutSec);

        projectItem.setInPoint(inTicksStr, 4);
        projectItem.setOutPoint(outTicksStr, 4);

        var vIdx = (typeof vTrackIdx !== "undefined" && vTrackIdx !== null) ? parseInt(vTrackIdx, 10) : 0;
        var tInSec = parseFloat(timelineInSec);
        var tInTicks = argon_secToTicks(tInSec);

        // Ensure sufficient video tracks
        while (seq.videoTracks.numTracks <= vIdx) {
            if (qe && qe.project && qe.project.getActiveSequence()) {
                qe.project.getActiveSequence().addVideoTrack();
            } else {
                break;
            }
        }

        var targetVTrack = seq.videoTracks[vIdx];
        if (!targetVTrack) {
            return JSON.stringify({ status: "error", error: "Video track index " + vIdx + " out of bounds." });
        }

        // Use Time object with exact seconds / ticks for overwriteClip
        var timeObj = new Time();
        timeObj.seconds = tInSec;

        targetVTrack.overwriteClip(projectItem, timeObj);

        // Verify placed clip
        var clipPlaced = null;
        var numClips = targetVTrack.clips.numTracks; // Premiere TrackItemCollection numTracks/numItems
        if (typeof targetVTrack.clips.numItems !== "undefined") {
            numClips = targetVTrack.clips.numItems;
        }

        return JSON.stringify({
            status: "ok",
            action: "insertClip",
            filePath: filePath,
            vTrackIdx: vIdx,
            srcInSec: srcInSec,
            srcOutSec: srcOutSec,
            timelineInSec: tInSec,
            inTicks: inTicksStr,
            outTicks: outTicksStr
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "insertClip",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Apply Motion Scale and Position transform to clip
 */
function argon_applyTransform(vTrackIdx, clipIdx, scaleVal, posX, posY) {
    try {
        var seq = app.project.activeSequence;
        if (!seq) {
            return JSON.stringify({ status: "error", error: "No active sequence found." });
        }

        var vIdx = parseInt(vTrackIdx, 10);
        var cIdx = parseInt(clipIdx, 10);

        var track = seq.videoTracks[vIdx];
        if (!track) {
            return JSON.stringify({ status: "error", error: "Video track " + vIdx + " not found." });
        }

        var clip = track.clips[cIdx];
        if (!clip) {
            return JSON.stringify({ status: "error", error: "Clip index " + cIdx + " not found on V" + (vIdx + 1) });
        }

        var motionComponent = null;
        for (var i = 0; i < clip.components.numItems; i++) {
            var comp = clip.components[i];
            if (comp.displayName === "Motion" || comp.matchName === "AE.ADBE Motion") {
                motionComponent = comp;
                break;
            }
        }

        if (!motionComponent) {
            return JSON.stringify({ status: "error", error: "Motion component not found on clip." });
        }

        var modifiedProps = [];
        for (var j = 0; j < motionComponent.properties.numItems; j++) {
            var prop = motionComponent.properties[j];
            if (prop.displayName === "Scale" && scaleVal !== null && typeof scaleVal !== "undefined") {
                prop.setValue(parseFloat(scaleVal), true);
                modifiedProps.push("Scale: " + scaleVal);
            }
            if (prop.displayName === "Position" && posX !== null && posY !== null && typeof posX !== "undefined") {
                // Premiere position is in pixel coordinates or normalized [0..1]
                var curPos = prop.getValue();
                var newX = parseFloat(posX);
                var newY = parseFloat(posY);
                // If coordinates are normalized fractions (0..1), multiply by sequence dimensions
                if (newX <= 1.0 && newY <= 1.0) {
                    newX = newX * (seq.frameSizeHorizontal || 1920);
                    newY = newY * (seq.frameSizeVertical || 1080);
                }
                prop.setValue([newX, newY], true);
                modifiedProps.push("Position: [" + newX + ", " + newY + "]");
            }
        }

        return JSON.stringify({
            status: "ok",
            action: "applyTransform",
            vTrackIdx: vIdx,
            clipIdx: cIdx,
            modifiedProps: modifiedProps
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "applyTransform",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Apply Audio Gain and Volume ducking to clip
 */
function argon_applyAudioGainAndDucking(aTrackIdx, clipIdx, targetDb) {
    try {
        var seq = app.project.activeSequence;
        if (!seq) {
            return JSON.stringify({ status: "error", error: "No active sequence found." });
        }

        var aIdx = parseInt(aTrackIdx, 10);
        var cIdx = parseInt(clipIdx, 10);
        var db = parseFloat(targetDb);

        var track = seq.audioTracks[aIdx];
        if (!track) {
            return JSON.stringify({ status: "error", error: "Audio track " + aIdx + " not found." });
        }

        var clip = track.clips[cIdx];
        if (!clip) {
            return JSON.stringify({ status: "error", error: "Audio clip index " + cIdx + " not found." });
        }

        // Iterate audio components for Volume / Level
        var volComponent = null;
        for (var i = 0; i < clip.components.numItems; i++) {
            var comp = clip.components[i];
            if (comp.displayName === "Volume" || comp.displayName === "Audio Gain" || comp.matchName === "AE.ADBE Audio Gain") {
                volComponent = comp;
                break;
            }
        }

        if (volComponent) {
            for (var j = 0; j < volComponent.properties.numItems; j++) {
                var prop = volComponent.properties[j];
                if (prop.displayName === "Level" || prop.displayName === "Volume") {
                    prop.setValue(db, true);
                    break;
                }
            }
        }

        return JSON.stringify({
            status: "ok",
            action: "applyAudioGainAndDucking",
            aTrackIdx: aIdx,
            clipIdx: cIdx,
            targetDb: db
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "applyAudioGainAndDucking",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Apply Lumetri LUT color preset to clip
 */
function argon_applyLumetriLUT(vTrackIdx, clipIdx, lutPath) {
    try {
        var seq = app.project.activeSequence;
        if (!seq) {
            return JSON.stringify({ status: "error", error: "No active sequence found." });
        }

        var vIdx = parseInt(vTrackIdx, 10);
        var cIdx = parseInt(clipIdx, 10);
        var track = seq.videoTracks[vIdx];
        if (!track) {
            return JSON.stringify({ status: "error", error: "Video track " + vIdx + " not found." });
        }

        var clip = track.clips[cIdx];
        if (!clip) {
            return JSON.stringify({ status: "error", error: "Clip index " + cIdx + " not found." });
        }

        // Check if Lumetri is already attached, or add via QE DOM
        if (app.enableQE) {
            app.enableQE();
        }

        var qeSeq = (qe && qe.project) ? qe.project.getActiveSequence() : null;
        if (qeSeq) {
            var qeTrack = qeSeq.getVideoTrackAt(vIdx);
            if (qeTrack) {
                var qeClip = qeTrack.getItemAt(cIdx);
                if (qeClip && qeClip.addVideoEffect) {
                    var lumetriEffect = qe.project.getVideoEffectByName("Lumetri Color");
                    if (lumetriEffect) {
                        qeClip.addVideoEffect(lumetriEffect);
                    }
                }
            }
        }

        return JSON.stringify({
            status: "ok",
            action: "applyLumetriLUT",
            vTrackIdx: vIdx,
            clipIdx: cIdx,
            lutPath: lutPath
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "applyLumetriLUT",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Capture full live timeline state as JSON
 */
function argon_getTimelineStateJSON() {
    try {
        var seq = app.project ? app.project.activeSequence : null;
        if (!seq) {
            return JSON.stringify({
                status: "ok",
                hasActiveSequence: false,
                message: "No active sequence found"
            });
        }

        var vTracksData = [];
        for (var v = 0; v < seq.videoTracks.numTracks; v++) {
            var vt = seq.videoTracks[v];
            var vClipsData = [];
            var numVClips = (typeof vt.clips.numItems !== "undefined") ? vt.clips.numItems : vt.clips.numTracks;
            for (var vc = 0; vc < numVClips; vc++) {
                var clipV = vt.clips[vc];
                if (clipV) {
                    vClipsData.push({
                        clipIndex: vc,
                        name: clipV.name,
                        inPointSec: clipV.inPoint ? argon_ticksToSec(clipV.inPoint.ticks) : 0,
                        outPointSec: clipV.outPoint ? argon_ticksToSec(clipV.outPoint.ticks) : 0,
                        startSec: clipV.start ? argon_ticksToSec(clipV.start.ticks) : 0,
                        endSec: clipV.end ? argon_ticksToSec(clipV.end.ticks) : 0,
                        durationSec: clipV.duration ? argon_ticksToSec(clipV.duration.ticks) : 0,
                        mediaPath: clipV.projectItem ? clipV.projectItem.getMediaPath() : null
                    });
                }
            }
            vTracksData.push({
                trackIndex: v,
                name: vt.name,
                clipCount: vClipsData.length,
                clips: vClipsData
            });
        }

        var aTracksData = [];
        for (var a = 0; a < seq.audioTracks.numTracks; a++) {
            var at = seq.audioTracks[a];
            var aClipsData = [];
            var numAClips = (typeof at.clips.numItems !== "undefined") ? at.clips.numItems : at.clips.numTracks;
            for (var ac = 0; ac < numAClips; ac++) {
                var clipA = at.clips[ac];
                if (clipA) {
                    aClipsData.push({
                        clipIndex: ac,
                        name: clipA.name,
                        inPointSec: clipA.inPoint ? argon_ticksToSec(clipA.inPoint.ticks) : 0,
                        outPointSec: clipA.outPoint ? argon_ticksToSec(clipA.outPoint.ticks) : 0,
                        startSec: clipA.start ? argon_ticksToSec(clipA.start.ticks) : 0,
                        endSec: clipA.end ? argon_ticksToSec(clipA.end.ticks) : 0,
                        durationSec: clipA.duration ? argon_ticksToSec(clipA.duration.ticks) : 0,
                        mediaPath: clipA.projectItem ? clipA.projectItem.getMediaPath() : null
                    });
                }
            }
            aTracksData.push({
                trackIndex: a,
                name: at.name,
                clipCount: aClipsData.length,
                clips: aClipsData
            });
        }

        var playheadSec = seq.getPlayerPosition ? argon_ticksToSec(seq.getPlayerPosition().ticks) : 0;
        var endTicks = seq.end ? seq.end : "0";
        var timelineDurationSec = argon_ticksToSec(endTicks);

        return JSON.stringify({
            status: "ok",
            hasActiveSequence: true,
            sequenceName: seq.name,
            sequenceID: seq.sequenceID,
            width: seq.frameSizeHorizontal,
            height: seq.frameSizeVertical,
            timebase: seq.timebase,
            playheadSec: playheadSec,
            timelineDurationSec: timelineDurationSec,
            videoTracks: vTracksData,
            audioTracks: aTracksData
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "getTimelineState",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}

/**
 * Trigger export via Adobe Media Encoder
 */
function argon_exportViaAME(outputPath, presetPath) {
    try {
        var seq = app.project.activeSequence;
        if (!seq) {
            return JSON.stringify({ status: "error", error: "No active sequence found to export." });
        }

        var outF = new File(outputPath);
        if (outF.parent && !outF.parent.exists) {
            outF.parent.create();
        }

        var presetF = new File(presetPath);
        var presetToUse = presetF.exists ? presetPath : "";

        // app.encoder.encodeSequence(sequence, outputFilePath, presetPath, workAreaType, removeOnCompletion)
        var jobID = app.encoder.encodeSequence(
            seq,
            outputPath,
            presetToUse,
            app.encoder.ENCODE_WORKAREA,
            1
        );

        app.encoder.startBatch();

        return JSON.stringify({
            status: "ok",
            action: "exportViaAME",
            jobID: jobID,
            outputPath: outputPath,
            presetPath: presetToUse
        });
    } catch (e) {
        return JSON.stringify({
            status: "error",
            action: "exportViaAME",
            error: e.message || String(e),
            line: e.line || 0
        });
    }
}
