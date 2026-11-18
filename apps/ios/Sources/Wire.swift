import Foundation

enum Wire {
    static func packet(_ type: UInt8, _ body: Data = Data(), seq: UInt64 = 0,
                       pts: UInt64 = 0, key: Bool = false) -> Data {
        var data = Data([85,67,83,49,1,type,0,key ? 1 : 0])
        append(UInt32(body.count), to: &data)
        append(seq, to: &data); append(pts, to: &data)
        append(UInt32(0), to: &data); data.append(body)
        return data
    }
    static func append<T: FixedWidthInteger>(_ number: T, to data: inout Data) {
        var big = number.bigEndian
        withUnsafeBytes(of: &big) { data.append(contentsOf: $0) }
    }
    static func number(_ data: Data, _ start: Int, _ count: Int) -> UInt64 {
        data.subdata(in: start..<(start+count)).reduce(0) { ($0 << 8) | UInt64($1) }
    }
}
