import Foundation

/// Lossless JSON representation. Assistant content blocks are stored and
/// replayed through this type verbatim — typed structs would drop unknown
/// fields and corrupt thinking-block signatures on replay.
enum JSONValue: Codable, Equatable, Sendable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let i = try? container.decode(Int.self) {
            self = .int(i)
        } else if let d = try? container.decode(Double.self) {
            self = .double(d)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let a = try? container.decode([JSONValue].self) {
            self = .array(a)
        } else if let o = try? container.decode([String: JSONValue].self) {
            self = .object(o)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let b): try container.encode(b)
        case .int(let i): try container.encode(i)
        case .double(let d): try container.encode(d)
        case .string(let s): try container.encode(s)
        case .array(let a): try container.encode(a)
        case .object(let o): try container.encode(o)
        }
    }
}

// MARK: - Read-only projection helpers (display/parsing only — never re-encode through these)

extension JSONValue {
    var stringValue: String? {
        if case .string(let s) = self { return s }
        return nil
    }

    var intValue: Int? {
        switch self {
        case .int(let i): return i
        case .double(let d): return Int(exactly: d)
        default: return nil
        }
    }

    var objectValue: [String: JSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }

    var arrayValue: [JSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }

    subscript(key: String) -> JSONValue? {
        objectValue?[key]
    }

    /// Content-block "type" discriminator.
    var blockType: String? {
        self["type"]?.stringValue
    }

    /// Recursively collects every string value stored under `key`, in
    /// document order. Used to harvest file_ids from server tool results
    /// whose exact inner shape varies by tool.
    func collectStrings(forKey key: String) -> [String] {
        switch self {
        case .object(let o):
            var found: [String] = []
            // Sorted for deterministic order within one object; nesting
            // order still dominates because results arrive per block.
            for (k, v) in o.sorted(by: { $0.key < $1.key }) {
                if k == key, let s = v.stringValue {
                    found.append(s)
                }
                found.append(contentsOf: v.collectStrings(forKey: key))
            }
            return found
        case .array(let a):
            return a.flatMap { $0.collectStrings(forKey: key) }
        default:
            return []
        }
    }
}

// MARK: - Mutation helpers for stream reassembly (used only by MessageAccumulator)

extension JSONValue {
    /// Appends `delta` to the string stored at `key` (creating it if absent).
    mutating func appendString(_ delta: String, toKey key: String) {
        guard case .object(var o) = self else { return }
        let existing = o[key]?.stringValue ?? ""
        o[key] = .string(existing + delta)
        self = .object(o)
    }

    mutating func setValue(_ value: JSONValue, forKey key: String) {
        guard case .object(var o) = self else { return }
        o[key] = value
        self = .object(o)
    }
}
