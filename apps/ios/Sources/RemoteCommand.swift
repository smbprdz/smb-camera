import Foundation

enum RemoteValue: Decodable,Equatable {
    case number(Double)
    case text(String)
    init(from decoder:Decoder) throws {
        let value=try decoder.singleValueContainer()
        if let number=try? value.decode(Double.self),number.isFinite { self = .number(number) }
        else if let text=try? value.decode(String.self) { self = .text(text) }
        else { throw RemoteError.invalid }
    }
}
enum RemoteError: Error { case invalid }
struct RemoteCommand: Decodable,Equatable {
    let session:String
    let revision:UInt64
    let request:String
    let control:String
    let value:RemoteValue
    static func parse(_ data:Data) throws -> RemoteCommand {
        guard data.count<=65536,
              let object=try JSONSerialization.jsonObject(with:data) as? [String:Any],
              Set(object.keys)==Set(["session","revision","request","control","value"]) else { throw RemoteError.invalid }
        let command=try JSONDecoder().decode(RemoteCommand.self,from:data)
        let ascii=CharacterSet(charactersIn:"0123456789abcdef")
        guard command.session.count==32,command.session.unicodeScalars.allSatisfy(ascii.contains),
              command.request.count==32,command.request.unicodeScalars.allSatisfy(ascii.contains),
              command.revision>0,command.revision<=9_007_199_254_740_992 else { throw RemoteError.invalid }
        switch (command.control,command.value) {
        case ("zoom",.number(let value)):guard value>=1 && value<=1024 else { throw RemoteError.invalid }
        case ("exposure_bias",.number(let value)):guard value>=(-128) && value<=128 else { throw RemoteError.invalid }
        case ("focus",.number(let value)):guard value>=0 && value<=1 else { throw RemoteError.invalid }
        case ("focus",.text(let text)):guard text=="auto" else { throw RemoteError.invalid }
        case ("lens",.text(let text)):
            guard !text.isEmpty,text.count<=256,!text.unicodeScalars.contains(where:CharacterSet.controlCharacters.contains) else { throw RemoteError.invalid }
        default:throw RemoteError.invalid
        }
        return command
    }
    func contextMatches(session:String,revision:UInt64) -> Bool { self.session==session && self.revision==revision }
}
