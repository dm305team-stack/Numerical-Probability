import Foundation

/// Files API client — used to fetch the PDF report that code execution
/// creates in the sandbox. Only sandbox-created files are downloadable.
struct FileDownloader: Sendable {
    struct Metadata: Sendable {
        let id: String
        let filename: String
        let mimeType: String?
        let sizeBytes: Int?
    }

    private static let betaHeader = "files-api-2025-04-14"
    private let session = URLSession(configuration: .ephemeral)

    func metadata(fileID: String, apiKey: String) async throws -> Metadata {
        let json = try await get(path: "v1/files/\(fileID)", apiKey: apiKey)
        let decoded = try JSONDecoder().decode(JSONValue.self, from: json)
        return Metadata(
            id: decoded["id"]?.stringValue ?? fileID,
            filename: decoded["filename"]?.stringValue ?? fileID,
            mimeType: decoded["mime_type"]?.stringValue,
            sizeBytes: decoded["size_bytes"]?.intValue
        )
    }

    func download(fileID: String, apiKey: String) async throws -> Data {
        try await get(path: "v1/files/\(fileID)/content", apiKey: apiKey)
    }

    private func get(path: String, apiKey: String) async throws -> Data {
        var request = URLRequest(url: AnthropicClient.baseURL.appendingPathComponent(path))
        request.httpMethod = "GET"
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.setValue(AnthropicClient.apiVersion, forHTTPHeaderField: "anthropic-version")
        request.setValue(Self.betaHeader, forHTTPHeaderField: "anthropic-beta")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw RunError.network("No HTTP response")
        }
        guard http.statusCode == 200 else {
            if let json = try? JSONDecoder().decode(JSONValue.self, from: data),
               let type = json["error"]?["type"]?.stringValue {
                throw RunError.http(
                    status: http.statusCode,
                    type: type,
                    message: json["error"]?["message"]?.stringValue ?? "")
            }
            throw RunError.http(status: http.statusCode, type: "unknown_error", message: "")
        }
        return data
    }
}
