import SwiftUI
import UIKit

/// Keeps capture foreground with a black OLED view. This does not power off the display.
@MainActor final class CameraScreenMode: ObservableObject {
    @Published private(set) var covered = false
    private var streaming = false
    private var active = true
    private var revealed = false
    private var brightness: CGFloat?
    private var idleTimer: Bool?
    private let recoveryKey = "ucs.screen.previousBrightness"

    init() {
        // Recover on next launch if the process was terminated before normal cleanup.
        if let previous = UserDefaults.standard.object(forKey: recoveryKey) as? NSNumber {
            UIScreen.main.brightness = CGFloat(previous.doubleValue)
            UserDefaults.standard.removeObject(forKey: recoveryKey)
        }
    }

    func setStreaming(_ value: Bool) {
        if streaming != value { revealed = false }
        streaming = value
        update()
    }

    func setActive(_ value: Bool) { active = value; update() }
    func reveal() { revealed = true; update() }
    func cover() { revealed = false; update() }

    private func restoreBrightness() {
        if let previous = brightness {
            UIScreen.main.brightness = previous
            brightness = nil
            UserDefaults.standard.removeObject(forKey: recoveryKey)
        }
    }

    private func update() {
        let capturing = streaming && active
        if capturing {
            if idleTimer == nil { idleTimer = UIApplication.shared.isIdleTimerDisabled }
            UIApplication.shared.isIdleTimerDisabled = true
        } else if let previous = idleTimer {
            UIApplication.shared.isIdleTimerDisabled = previous
            idleTimer = nil
        }
        covered = capturing && !revealed
        if covered {
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            if brightness == nil {
                brightness = UIScreen.main.brightness
                UserDefaults.standard.set(Double(brightness!), forKey: recoveryKey)
            }
            UIScreen.main.brightness = 0
        } else { restoreBrightness() }
    }
}
