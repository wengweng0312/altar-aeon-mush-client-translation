param([string]$SessionFile)
$ErrorActionPreference="Stop"
$mutex=New-Object Threading.Mutex($false,"Local\MushZTranslationSpeechWorker")
if(-not $mutex.WaitOne(0)){exit 0}
$bridge=Split-Path -Parent $MyInvocation.MyCommand.Path
$inbox=Join-Path $bridge "speech_inbox"
New-Item -ItemType Directory -Force -Path $inbox | Out-Null
$candidates=@(
 (Join-Path (Split-Path -Parent $bridge) "nvdaControllerClient32.dll"),
 (Join-Path (Split-Path -Parent (Split-Path -Parent $bridge)) "nvdaControllerClient32.dll"),
 (Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $bridge))) "nvdaControllerClient32.dll"),
 (Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $bridge)))) "nvdaControllerClient32.dll")
)
$dll=$candidates|Where-Object{Test-Path $_}|Select-Object -First 1
if(-not $dll){exit 2}
$escaped=$dll.Replace('\','\\')
$code=@"
using System;
using System.Runtime.InteropServices;
public static class MushZNvda {
 [DllImport("$escaped",CharSet=CharSet.Unicode,CallingConvention=CallingConvention.Cdecl)]
 public static extern int nvdaController_speakText(string text);
}
"@
Add-Type -TypeDefinition $code
function Test-SessionAlive {
 if([string]::IsNullOrWhiteSpace($SessionFile)){return $true}
 try{
  if(-not (Test-Path -LiteralPath $SessionFile)){return $false}
  return (((Get-Date) - (Get-Item -LiteralPath $SessionFile).LastWriteTime).TotalSeconds -le 5)
 }catch{return $false}
}
try{while(Test-SessionAlive){
 $files=@(Get-ChildItem -LiteralPath $inbox -Filter "*.txt" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc,Name)
 foreach($item in $files){
  $remove=$false
  try{
   $hex=([IO.File]::ReadAllText($item.FullName)).Trim()
   if($hex.Length -gt 0 -and $hex.Length%2 -eq 0){
    $bytes=New-Object byte[] ($hex.Length/2)
    for($i=0;$i-lt$bytes.Length;$i++){$bytes[$i]=[Convert]::ToByte($hex.Substring($i*2,2),16)}
    $remove=([MushZNvda]::nvdaController_speakText([Text.Encoding]::UTF8.GetString($bytes)) -eq 0)
   }else{
    $remove=$true
   }
  }catch{}
  if($remove){
   Remove-Item -LiteralPath $item.FullName -Force -ErrorAction SilentlyContinue
  }else{
   break
  }
 }
 Start-Sleep -Milliseconds 100
}}finally{$mutex.ReleaseMutex();$mutex.Dispose()}
