// Copy this file into the event's Apps Script project. Replace API_SECRET and
// the SOURCES placeholders in that editor only. Never commit the real secret
// or source IDs from the deployed copy. API_SECRET must be at least 32 random
// bytes encoded as 64 hex characters or 43+ URL-safe characters.
const API_SECRET = "REPLACE_ME";
const SOURCES = {
  participants: {
    spreadsheet_id: "REPLACE_WITH_PARTICIPANTS_SPREADSHEET_ID",
    sheet_name: "REPLACE_WITH_PARTICIPANTS_SHEET_NAME",
    timestamp_column: 0,
    timestamp_header: "REPLACE_WITH_PARTICIPANTS_TIMESTAMP_HEADER"
  },
  leaders: {
    spreadsheet_id: "REPLACE_WITH_LEADERS_SPREADSHEET_ID",
    sheet_name: "REPLACE_WITH_LEADERS_SHEET_NAME",
    timestamp_column: 0,
    timestamp_header: "REPLACE_WITH_LEADERS_TIMESTAMP_HEADER"
  }
};

function doPost(e) {
  try {
    return jsonResponse_(handlePost_(e, {
      secret: API_SECRET,
      sources: SOURCES,
      openById: function (id) { return SpreadsheetApp.openById(id); },
      formatDate: function (value, timezone) {
        return Utilities.formatDate(value, timezone, "yyyy-MM-dd HH:mm:ss");
      }
    }));
  } catch (_) {
    return jsonResponse_({ ok: false, error: "source_error" });
  }
}

function doGet() {
  return jsonResponse_({ ok: false, error: "bad_request" });
}

// Run once from the editor as the deploying account to grant Sheet access.
// This checks each configured tab/header but never reads registration rows.
function authorizeSources() {
  try {
    var sources = SOURCES;
    if (!sources || typeof sources !== "object" || Array.isArray(sources) || Object.keys(sources).length === 0) {
      throw new Error("invalid mapping");
    }
    Object.keys(sources).forEach(function (stream) {
      var source = sources[stream];
      if ((stream !== "participants" && stream !== "leaders") || !source || typeof source !== "object" ||
          typeof source.spreadsheet_id !== "string" || !source.spreadsheet_id ||
          typeof source.sheet_name !== "string" || !source.sheet_name ||
          !Number.isInteger(source.timestamp_column) || source.timestamp_column < 1 ||
          typeof source.timestamp_header !== "string" || !source.timestamp_header) {
        throw new Error("invalid mapping");
      }
      var spreadsheet = SpreadsheetApp.openById(source.spreadsheet_id);
      var sheet = spreadsheet.getSheetByName(source.sheet_name);
      if (!sheet || sheet.getRange(1, source.timestamp_column).getValue() !== source.timestamp_header) {
        throw new Error("source mismatch");
      }
    });
    console.log("Source access authorized; configured headers verified.");
    return "Source access authorized; configured headers verified.";
  } catch (_) {
    throw new Error("Unable to access configured source sheets or headers.");
  }
}

function handlePost_(e, deps) {
  if (!configuredSecret_(deps.secret)) return { ok: false, error: "source_error" };
  var request;
  try {
    if (!e || !e.postData || typeof e.postData.contents !== "string" ||
        typeof e.postData.type !== "string" ||
        e.postData.type.toLowerCase().split(";")[0].trim() !== "application/json") {
      return { ok: false, error: "bad_request" };
    }
    request = JSON.parse(e.postData.contents);
  } catch (_) {
    return { ok: false, error: "bad_request" };
  }
  if (!request || typeof request !== "object" || Array.isArray(request) ||
      Object.keys(request).sort().join(",") !== "secret,stream" ||
      typeof request.secret !== "string" || typeof request.stream !== "string") {
    return { ok: false, error: "bad_request" };
  }
  if (request.secret !== deps.secret) return { ok: false, error: "unauthorized" };
  if (request.stream !== "participants" && request.stream !== "leaders") {
    return { ok: false, error: "unknown_stream" };
  }

  try {
    var source = deps.sources && deps.sources[request.stream];
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      return { ok: false, error: "unknown_stream" };
    }
    if (typeof source.spreadsheet_id !== "string" || !source.spreadsheet_id ||
        typeof source.sheet_name !== "string" || !source.sheet_name ||
        !Number.isInteger(source.timestamp_column) || source.timestamp_column < 1 ||
        typeof source.timestamp_header !== "string" || !source.timestamp_header) {
      return { ok: false, error: "source_error" };
    }

    var spreadsheet = deps.openById(source.spreadsheet_id);
    var sheet = spreadsheet.getSheetByName(source.sheet_name);
    if (!sheet) return { ok: false, error: "source_error" };
    var timezone = spreadsheet.getSpreadsheetTimeZone();
    if (typeof timezone !== "string" || !timezone) return { ok: false, error: "source_error" };
    var header = sheet.getRange(1, source.timestamp_column).getValue();
    if (header !== source.timestamp_header) return { ok: false, error: "source_error" };

    var lastRow = sheet.getLastRow();
    var timestamps = [];
    if (lastRow > 1) {
      var values = sheet.getRange(2, source.timestamp_column, lastRow - 1, 1).getValues();
      for (var i = 0; i < values.length; i++) {
        timestamps.push(normalizeTimestamp_(values[i][0], timezone, deps.formatDate));
      }
    }
    return { ok: true, stream: request.stream, timezone: timezone, timestamps: timestamps };
  } catch (_) {
    return { ok: false, error: "source_error" };
  }
}

function configuredSecret_(secret) {
  return typeof secret === "string" &&
    (/^[0-9a-fA-F]{64,}$/.test(secret) || /^[A-Za-z0-9_-]{43,}$/.test(secret));
}

function normalizeTimestamp_(value, timezone, formatDate) {
  if (value instanceof Date) {
    if (!isFinite(value.getTime())) throw new Error("invalid timestamp");
    var formatted = formatDate(value, timezone);
    if (!isIsoTimestamp_(formatted)) throw new Error("invalid timestamp");
    return formatted;
  }
  if (typeof value !== "string") throw new Error("invalid timestamp");
  var match = /^(\d{1,2})\/(\d{1,2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("invalid timestamp");
  var month = Number(match[1]), day = Number(match[2]), year = Number(match[3]);
  var hour = Number(match[4]), minute = Number(match[5]), second = Number(match[6]);
  var check = new Date(0);
  check.setUTCFullYear(year, month - 1, day);
  check.setUTCHours(hour, minute, second, 0);
  if (year < 1 || check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 ||
      check.getUTCDate() !== day || hour > 23 || minute > 59 || second > 59) {
    throw new Error("invalid timestamp");
  }
  return pad4_(year) + "-" + pad2_(month) + "-" + pad2_(day) + " " +
    pad2_(hour) + ":" + pad2_(minute) + ":" + pad2_(second);
}

function isIsoTimestamp_(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) return false;
  var parts = value.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/);
  return normalizeTimestamp_(parts[2] + "/" + parts[3] + "/" + parts[1] + " " +
    parts[4] + ":" + parts[5] + ":" + parts[6], "", function () {}) === value;
}

function pad2_(value) { return ("0" + value).slice(-2); }
function pad4_(value) { return ("000" + value).slice(-4); }

function jsonResponse_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

// Run selfCheck() manually after copying the script. Synthetic rows only.
function selfCheck() {
  var secret = new Array(65).join("a");
  var opens = 0;
  var sampleValues = [
    ["Timestamp"],
    ["9/25/2026 13:24:26"],
    [new Date("2026-09-25T17:24:26Z")],
    [new Date("2026-01-15T17:24:26Z")],
    [new Date("2026-07-15T16:24:26Z")],
    [new Date("2026-09-25T03:30:00Z")]
  ];
  var source = { spreadsheet_id: "synthetic", sheet_name: "Form Responses 1",
    timestamp_column: 1, timestamp_header: "Timestamp" };
  var spreadsheet = fakeSpreadsheet_(sampleValues, "America/Detroit");
  assertSelfCheck_(!configuredSecret_("") && !configuredSecret_("REPLACE_ME"), "unconfigured secret rejection");
  var deps = {
    secret: secret,
    sources: { participants: source },
    openById: function () { opens++; return spreadsheet; },
    formatDate: function (value, timezone) {
      return Utilities.formatDate(value, timezone, "yyyy-MM-dd HH:mm:ss");
    }
  };
  var request = function (suppliedSecret, stream) {
    return handlePost_({ postData: { type: "application/json", contents:
      JSON.stringify({ secret: suppliedSecret, stream: stream }) } }, deps);
  };
  assertSelfCheck_(request("wrong", "participants").error === "unauthorized", "wrong secret");
  assertSelfCheck_(request("", "participants").error === "unauthorized", "missing secret");
  assertSelfCheck_(opens === 0, "authentication must precede Sheet access");
  assertSelfCheck_(request(secret, "unknown").error === "unknown_stream", "unknown stream");
  assertSelfCheck_(handlePost_({ postData: { type: "text/plain", contents: "{}" } }, deps).error ===
    "bad_request", "unexpected request type");

  var result = request(secret, "participants");
  assertSelfCheck_(result.ok === true, "valid request");
  assertSelfCheck_(result.timezone === "America/Detroit", "timezone");
  assertSelfCheck_(result.timestamps.join("|") === [
    "2026-09-25 13:24:26", "2026-09-25 13:24:26", "2026-01-15 12:24:26",
    "2026-07-15 12:24:26", "2026-09-24 23:30:00"
  ].join("|"), "local timestamp serialization");

  deps.sources = { participants: source };
  spreadsheet = fakeSpreadsheet_([["Timestamp"]], "America/Detroit");
  assertSelfCheck_(request(secret, "participants").timestamps.length === 0, "header-only sheet");
  spreadsheet = fakeSpreadsheet_([["Timestamp"], ["not a timestamp"]], "America/Detroit");
  assertSelfCheck_(request(secret, "participants").error === "source_error", "bad timestamp cell");
  assertSelfCheck_(normalizeTimestamp_("9/25/2026 13:24:26", "", function () {}) ===
    "2026-09-25 13:24:26", "text timestamp normalization");
  console.log("Apps Script self-check passed");
  return "Apps Script self-check passed";
}

function fakeSpreadsheet_(values, timezone) {
  var sheet = {
    getLastRow: function () { return values.length; },
    getRange: function (row, column, count) {
      return {
        getValue: function () { return values[row - 1] && values[row - 1][column - 1]; },
        getValues: function () {
          var result = [];
          for (var i = 0; i < count; i++) result.push([values[row - 1 + i] && values[row - 1 + i][column - 1]]);
          return result;
        }
      };
    }
  };
  return { getSheetByName: function () { return sheet; }, getSpreadsheetTimeZone: function () { return timezone; } };
}

function assertSelfCheck_(condition, name) {
  if (!condition) throw new Error("self-check failed: " + name);
}
