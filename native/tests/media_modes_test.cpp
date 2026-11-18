#include "../windows/bridge/media_modes.hpp"
#include <iostream>
#include <stdexcept>
using namespace ucs::bridge;
void require(bool value){if(!value)throw std::runtime_error("Media mode contract failed");}
int main(){try {
    for(const auto mode:{MediaMode{},MediaMode{1920,1080,60,1,3},MediaMode{1080,1920,30000,1001,2},MediaMode{3840,2160,60,1,2}})
        require(valid(mode) && duration_100ns(mode)>0);
    require(duration_100ns(MediaMode{1080,1920,30000,1001,2})==333667);
    require(duration_100ns(MediaMode{3840,2160,60,1,2})==166667);
    for(const auto mode:{MediaMode{0,1080},MediaMode{1920,1080,0},MediaMode{1920,1080,30,0},
         MediaMode{1920,1080,30,1,0},MediaMode{1920,1080,30,1,4},MediaMode{16384,16384,30,1,2},
         MediaMode{641,481,30,1,3},MediaMode{640,480,30,1,3,1}})require(!valid(mode));
    require(valid(MediaMode{641,481,30,1,2})); // Odd RGB dimensions are legal.
    require(!supports(MediaMode{640,480,30,1,2},PixelFormat::nv12));
    std::cout<<"{\"media_modes\":\"pass\",\"bounds_and_rational_duration\":true,\"capture_hardware\":false}\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
