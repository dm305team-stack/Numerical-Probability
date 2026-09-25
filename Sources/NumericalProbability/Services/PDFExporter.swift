import AppKit
import UniformTypeIdentifiers

/// Saves downloaded PDF bytes via the standard save panel.
@MainActor
enum PDFExporter {
    static func save(data: Data, suggestedFilename: String) -> URL? {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.pdf]
        // basename() — never trust a server-provided filename with paths.
        panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.canCreateDirectories = true

        guard panel.runModal() == .OK, let url = panel.url else {
            return nil
        }
        do {
            try data.write(to: url)
            return url
        } catch {
            NSAlert(error: error).runModal()
            return nil
        }
    }
}
