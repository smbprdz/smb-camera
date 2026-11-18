import Foundation

enum VideoMode: String, CaseIterable, Identifiable {
    case fullHD = "1080p30"
    case ultraHD = "4K30"
    var id: String { rawValue }
    var width: Int32 { self == .ultraHD ? 3840 : 1920 }
    var height: Int32 { self == .ultraHD ? 2160 : 1080 }
    var bitrate: Int { self == .ultraHD ? 36_000_000 : 12_000_000 }
    var fps: Int32 { 30 }
}

struct EncoderConfigurationError: LocalizedError {
    let operation: String
    let code: Int32
    var errorDescription: String? { "\(operation): \(code)" }
}
