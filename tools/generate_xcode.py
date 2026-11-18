"""Generate deterministic native Xcode project; no third-party generator required."""
from pathlib import Path
import hashlib
import plistlib

ROOT=Path(__file__).resolve().parents[1]/'apps/ios'
def ident(name): return hashlib.sha256(name.encode()).hexdigest()[:24].upper()
def main():
    project=ROOT/'UniversalCamera.xcodeproj';project.mkdir(exist_ok=True)
    objects=[]
    def obj(name,content): objects.append(f'{ident(name)} = {{ {content} }};');return ident(name)
    refs=[];builds=[]
    for source in sorted((ROOT/'Sources').glob('*.swift')):
        ref=obj('file-'+source.name,f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "Sources/{source.name}"; sourceTree = "<group>";')
        refs.append(ref)
        builds.append(obj('build-'+source.name,f'isa = PBXBuildFile; fileRef = {ref};'))
    assets=obj('assets','isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>";')
    refs.append(assets)
    asset_build=obj('assets-build',f'isa = PBXBuildFile; fileRef = {assets};')
    resources=obj('resources',f'isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ({asset_build},); runOnlyForDeploymentPostprocessing = 0;')
    product=obj('product','isa = PBXFileReference; explicitFileType = wrapper.application; path = UniversalCamera.app; sourceTree = BUILT_PRODUCTS_DIR;')
    products=obj('products',f'isa = PBXGroup; children = ({product},); name = Products; sourceTree = "<group>";')
    group=obj('group',f'isa = PBXGroup; children = ({",".join(refs+[products])},); sourceTree = "<group>";')
    sources=obj('sources',f'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ({",".join(builds)},); runOnlyForDeploymentPostprocessing = 0;')
    for level in ['project','target']:
        configs=[]
        for mode in ['Debug','Release']:
            settings='CLANG_ENABLE_MODULES = YES; SDKROOT = iphoneos; IPHONEOS_DEPLOYMENT_TARGET = 16.0; SWIFT_VERSION = 5.0;'
            if level=='target':
                settings+=' ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon; PRODUCT_BUNDLE_IDENTIFIER = com.simbaproduz.universalcamera; PRODUCT_NAME = UniversalCamera; INFOPLIST_FILE = Info.plist; TARGETED_DEVICE_FAMILY = 1; CODE_SIGN_STYLE = Automatic; MARKETING_VERSION = 0.9.0; CURRENT_PROJECT_VERSION = 9; SWIFT_OPTIMIZATION_LEVEL = '+('"-Onone";' if mode=='Debug' else '"-O";')
            configs.append(obj(level+mode,f'isa = XCBuildConfiguration; buildSettings = {{ {settings} }}; name = {mode};'))
        obj(level+'configs',f'isa = XCConfigurationList; buildConfigurations = ({",".join(configs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
    target=obj('target',f'isa = PBXNativeTarget; buildConfigurationList = {ident("targetconfigs")}; buildPhases = ({sources},{resources},); buildRules = (); dependencies = (); name = UniversalCamera; productName = UniversalCamera; productReference = {product}; productType = "com.apple.product-type.application";')
    root=obj('project',f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 1640; }}; buildConfigurationList = {ident("projectconfigs")}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en,Base); mainGroup = {group}; productRefGroup = {products}; projectDirPath = ""; projectRoot = ""; targets = ({target},);')
    (project/'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n'+'\n'.join(objects)+f'\n}}; rootObject = {root}; }}\n',encoding='utf-8',newline='\n')
    scheme=project/'xcshareddata/xcschemes';scheme.mkdir(parents=True,exist_ok=True)
    (scheme/'UniversalCamera.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1640" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="UniversalCamera.app" BlueprintName="UniversalCamera" ReferencedContainer="container:UniversalCamera.xcodeproj"/></BuildActionEntry></BuildActionEntries></BuildAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="UniversalCamera.app" BlueprintName="UniversalCamera" ReferencedContainer="container:UniversalCamera.xcodeproj"/></BuildableProductRunnable></LaunchAction>
<ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''',encoding='utf-8',newline='\n')
    info={'CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleExecutable':'$(EXECUTABLE_NAME)',
          'CFBundleName':'UniversalCamera','CFBundleDisplayName':'SMB Camera','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.9.0',
          'CFBundleVersion':'9','LSRequiresIPhoneOS':True,'UILaunchScreen':{},
          'NSMicrophoneUsageDescription':'Incluir sua voz na gravação original solicitada no PC pareado.',
          'NSCameraUsageDescription':'Ler o QR de pareamento e transmitir a camera para o seu computador.',
          'NSLocalNetworkUsageDescription':'Localizar seu PC pareado e enviar video pela sua rede local.',
          'NSBonjourServices':['_ucs-camera._tcp'],
          'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait','UIInterfaceOrientationLandscapeLeft','UIInterfaceOrientationLandscapeRight']}
    (ROOT/'Info.plist').write_bytes(plistlib.dumps(info,sort_keys=True))
    print('Xcode project generated:',project)
if __name__=='__main__': main()
