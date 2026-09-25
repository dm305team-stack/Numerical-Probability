import Foundation

/// One conversation turn, mirroring the Messages API shape.
/// User content is constructed via the builders below; assistant content is
/// captured raw from the stream and echoed back verbatim.
struct ApiMessage: Codable, Sendable {
    let role: String
    var content: [JSONValue]
}

enum MessageBuilder {
    static func textBlock(_ text: String, ephemeralCache: Bool = false) -> JSONValue {
        var block: [String: JSONValue] = [
            "type": .string("text"),
            "text": .string(text),
        ]
        if ephemeralCache {
            block["cache_control"] = .object(["type": .string("ephemeral")])
        }
        return .object(block)
    }

    static func documentBlock(base64: String, title: String, oneHourCache: Bool = false) -> JSONValue {
        var block: [String: JSONValue] = [
            "type": .string("document"),
            "source": .object([
                "type": .string("base64"),
                "media_type": .string("application/pdf"),
                "data": .string(base64),
            ]),
            "title": .string(title),
        ]
        if oneHourCache {
            block["cache_control"] = .object([
                "type": .string("ephemeral"),
                "ttl": .string("1h"),
            ])
        }
        return .object(block)
    }
}

enum RequestBuilder {
    static let model = "claude-opus-4-8"
    static let maxTokens = 64000

    /// Full /v1/messages request body. Built as JSONValue and encoded with
    /// .sortedKeys so identical logical requests are byte-identical —
    /// anything else silently kills the prompt cache.
    static func messagesBody(
        systemPrompt: String,
        messages: [ApiMessage],
        container: String?
    ) -> JSONValue {
        var body: [String: JSONValue] = [
            "model": .string(model),
            "max_tokens": .int(maxTokens),
            "stream": .bool(true),
            "thinking": .object([
                "type": .string("adaptive"),
                "display": .string("summarized"),
            ]),
            "tools": .array([
                .object([
                    "type": .string("code_execution_20260120"),
                    "name": .string("code_execution"),
                ])
            ]),
            "system": .array([
                .object([
                    "type": .string("text"),
                    "text": .string(systemPrompt),
                ])
            ]),
            "messages": .array(messages.map { message in
                .object([
                    "role": .string(message.role),
                    "content": .array(message.content),
                ])
            }),
        ]
        if let container {
            body["container"] = .string(container)
        }
        return .object(body)
    }

    static func encode(_ body: JSONValue) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(body)
    }
}
