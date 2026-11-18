import Foundation
let bytes = Wire.packet(4,seq:2,pts:3)
let hex = bytes.map { String(format:"%02x",$0) }.joined()
precondition(hex == "5543533101040000000000000000000000000002000000000000000300000000")
precondition(Wire.number(bytes,12,8) == 2)
precondition(Wire.number(bytes,20,8) == 3)
print("Swift UCS1 golden vector PASS")

let pin = String(repeating:"a",count:64)
let secret = String(repeating:"b",count:64)
let uri = "universalcamera://pair?v=1&host=192.168.0.82&name=Meu%20PC%20%2B%20camera&pin=" + pin + "&token=" + secret
let pairing = try PairingRecord.parse(uri)
precondition(pairing.name == "Meu PC + camera")
precondition(pairing.serviceName == "UCS-" + String(pin.prefix(16)))
let restored = try JSONDecoder().decode(PairingRecord.self,from:JSONEncoder().encode(pairing))
precondition(restored == pairing)
let invalid = [uri + "&host=192.168.0.1", uri + "&extra=1", uri.replacingOccurrences(of:"v=1",with:"v=2"),
    uri.replacingOccurrences(of:"192.168.0.82",with:"8.8.8.8"),
    uri.replacingOccurrences(of:"192.168.0.82",with:"127.0.0.1"),
    uri.replacingOccurrences(of:"192.168.0.82",with:"169.254.1.2"),
    uri.replacingOccurrences(of:"192.168.0.82",with:"192.168.000.82"),
    uri.replacingOccurrences(of:"universalcamera:",with:"https:"),
    uri.replacingOccurrences(of:"//pair?",with:"//pair:443?"),uri + "#fragment",
    uri.replacingOccurrences(of:"name=Meu",with:"name=%00Meu"),
    uri.replacingOccurrences(of:pin,with:String(pin.dropLast())),
    uri.replacingOccurrences(of:secret,with:String(repeating:"g",count:64))]
for value in invalid {
    do { _ = try PairingRecord.parse(value); fatalError("Invalid pairing accepted") }
    catch PairingError.invalid { }
}
print("Swift pairing parser: valid round-trip and \(invalid.count) rejected cases PASS")

var clock = ClockEstimate()
clock.observe(t1:1000,t2:11050,t3:11100,t4:1150)
precondition(clock.offsetUs == 10000 && clock.uncertaintyUs == 50)
clock.observe(t1:2000,t2:12000,t3:12000,t4:3000)
precondition(clock.uncertaintyUs == 50)
clock.observe(t1:500,t2:100,t3:90,t4:700)
precondition(clock.offsetUs == 10000)
print("Swift four-timestamp clock estimate PASS")
precondition(VideoMode.ultraHD.width == 3840 && VideoMode.ultraHD.height == 2160 && VideoMode.ultraHD.fps == 30)
precondition(VideoMode.fullHD.width == 1920 && VideoMode.ultraHD.bitrate > VideoMode.fullHD.bitrate)
print("Swift capture modes: 1080p30 and 4K30 PASS")

let session=String(repeating:"a",count:32)
let requestID=String(repeating:"b",count:32)
func commandData(_ overrides:[String:Any]=[:]) throws -> Data {
    let base:[String:Any]=["session":session,"revision":1,"request":requestID,"control":"zoom","value":2.0]
    return try JSONSerialization.data(withJSONObject:base.merging(overrides) { _,new in new })
}
let zoomCommand=try RemoteCommand.parse(commandData())
precondition(zoomCommand.contextMatches(session:session,revision:1))
precondition(!zoomCommand.contextMatches(session:session,revision:2))
precondition(!zoomCommand.contextMatches(session:requestID,revision:1))
_ = try RemoteCommand.parse(commandData(["control":"focus","value":"auto"]))
_ = try RemoteCommand.parse(commandData(["control":"focus","value":0.4]))
_ = try RemoteCommand.parse(commandData(["control":"lens","value":"camera-wide"]))
_ = try RemoteCommand.parse(commandData(["control":"exposure_bias","value":-2.0]))
let badCommands:[[String:Any]] = [["value":true],["value":0],["value":1025],
    ["control":"focus","value":1.1],["control":"focus","value":"unknown"],
    ["control":"lens","value":""],["control":"lens","value":"a\n"],
    ["control":"exposure_bias","value":129],["control":"exposure_bias","value":true],["control":"exposure_bias","value":"auto"],
    ["control":"system","value":1],["session":"short"],["request":"short"],
    ["revision":0],["revision":true],["extra":"unexpected"]]
for invalid in badCommands {
    do { _ = try RemoteCommand.parse(commandData(invalid));fatalError("Invalid camera command accepted") }
    catch { }
}
print("Swift remote controls: context, valid commands and \(badCommands.count) invalid cases PASS")
