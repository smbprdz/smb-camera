// Synthetic producer for the isolated IPC proof. No camera, audio or disk video.
#include "pipe_windows.hpp"
#include <iostream>
#include <string_view>
#include <fstream>

int wmain(int argc,wchar_t** argv) {
    using namespace ucs::bridge;
    try {
        if(argc<5 || std::wstring_view(argv[1])!=L"--pipe" || std::wstring_view(argv[3])!=L"--epoch")return 2;
        const std::wstring name=argv[2];const auto epoch=std::stoull(argv[4]);
        const bool invalid=argc==6 && std::wstring_view(argv[5])==L"--invalid-header";
        const bool stall=argc==6 && std::wstring_view(argv[5])==L"--stall";
        if(!epoch || !valid_name(name) || (argc!=5 && !(invalid||stall)))return 2;
        Handle server(create_server(name));if(!server)throw std::runtime_error("Named pipe creation failed");
        Handle ready(OpenEventW(EVENT_MODIFY_STATE,FALSE,ready_name(name,epoch).c_str()));if(ready)SetEvent(ready.value);
        const auto started=GetTickCount64();std::vector<BYTE> packet;
        for(;;) {
            if(!connected(server.value)){DisconnectNamedPipe(server.value);continue;}
            Request request{};
            while(read_request(server.value,request)) {
                if(stall)Sleep(5000);
                const auto tick=GetTickCount64();const auto id=(tick-started)*30/1000+1;
                FrameDescriptor frame{};frame.format=request.format;frame.width=request.width;frame.height=request.height;
                frame.stride0=request.width*(request.format==PixelFormat::nv12?1:4);
                frame.stride1=request.format==PixelFormat::nv12?request.width:0;
                frame.plane1_offset=request.format==PixelFormat::nv12?request.width*request.height:0;
                frame.color_space=request.format==PixelFormat::nv12?ucs::native::ColorSpace::bt709_limited_sdr:ucs::native::ColorSpace::srgb_full;
                frame.payload_bytes=payload_size(request);frame.frame_id=id;frame.pts_100ns=static_cast<std::int64_t>((id-1)*333333);
                Reply reply{};reply.epoch=epoch;reply.captured_tick_ms=tick;
                reply.body_bytes=static_cast<std::uint32_t>(sizeof(frame)+frame.payload_bytes);
                packet.resize(sizeof(reply)+reply.body_bytes);BYTE* pixels=packet.data()+sizeof(reply)+sizeof(frame);
                const auto level=static_cast<BYTE>(32+(id%16)*8);
                if(request.format==PixelFormat::nv12){std::memset(pixels,level,frame.plane1_offset);std::memset(pixels+frame.plane1_offset,128,static_cast<std::size_t>(frame.payload_bytes-frame.plane1_offset));}
                else for(std::size_t n=0;n<frame.payload_bytes;n+=4){pixels[n]=pixels[n+1]=pixels[n+2]=level;pixels[n+3]=255;}
                if(request.width>=20) {
                    constexpr BYTE marker[4]={'U','C','S','B'};
                    for(unsigned n=0;n<20;++n){const BYTE value=n<4?marker[n]:static_cast<BYTE>((id&(1ULL<<(n-4)))?235:16);
                        if(request.format==PixelFormat::nv12)pixels[n]=value;
                        else{pixels[n*4]=pixels[n*4+1]=pixels[n*4+2]=value;}}
                }
                if(invalid)reply.body_bytes=0x7fffffff;
                std::memcpy(packet.data(),&reply,sizeof(reply));std::memcpy(packet.data()+sizeof(reply),&frame,sizeof(frame));
                if(!write_reply(server.value,packet))break;
            }
            DisconnectNamedPipe(server.value);
        }
    } catch(const std::exception& error){const auto code=GetLastError();std::ofstream log("producer.stderr.log",std::ios::app);log<<"Producer: "<<error.what()<<" win32="<<code<<'\n';std::cerr<<"Producer: "<<error.what()<<" win32="<<code<<'\n';return 1;}
}
