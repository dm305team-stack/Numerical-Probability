import SwiftUI
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Bare SPM binaries launch as accessory processes behind the terminal;
        // force regular activation so the window, menu bar, and panels work.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

@main
struct NumericalProbabilityApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            MainView()
                .environment(model)
                .frame(minWidth: 720, minHeight: 560)
        }
        .defaultSize(width: 860, height: 720)

        Settings {
            SettingsView()
                .environment(model)
        }
    }
}
