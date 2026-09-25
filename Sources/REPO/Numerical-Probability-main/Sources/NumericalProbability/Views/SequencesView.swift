import SwiftUI

struct SequencesView: View {
    @Environment(AppModel.self) private var model
    let result: RunResult

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Final Sequences", systemImage: "number.square.fill")
                    .font(.headline)
                Spacer()
                if result.pdfFileID != nil {
                    Button {
                        model.exportPDF()
                    } label: {
                        Label("Export PDF", systemImage: "arrow.down.document")
                    }
                }
            }

            if result.sequences.isEmpty {
                Text("Sequences were not machine-parsed — see the report above for the final list.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(result.sequences) { sequence in
                    HStack(spacing: 12) {
                        Text("\(sequence.index)")
                            .font(.callout.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .frame(width: 24, alignment: .trailing)
                        Text(sequence.display)
                            .font(.title3.monospaced().weight(.semibold))
                            .textSelection(.enabled)
                        Spacer()
                        if let probability = sequence.probabilityLabel {
                            Text(probability)
                                .font(.callout.monospaced())
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(.quaternary, in: Capsule())
                        }
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(sequence.display, forType: .string)
                        } label: {
                            Image(systemName: "doc.on.doc")
                        }
                        .buttonStyle(.borderless)
                        .help("Copy sequence")
                    }
                }
            }

            if let url = result.exportedURL {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("Saved to \(url.path)")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Button("Show in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                    .buttonStyle(.link)
                }
            }

            if let error = model.exportError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
        }
        .padding(14)
        .background(.quinary, in: RoundedRectangle(cornerRadius: 10))
    }
}
