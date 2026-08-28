// Preload do tileserver-gl (spec 003 / achado de 27/08/2026).
//
// A lib `pmtiles` lanca um Error nao tratado quando um HTTP Range Request do
// PMTiles remoto volta sem content-length. Sem este guard, esse Error mata o
// processo inteiro: o Docker reergue em ~1,5 s e, nesse intervalo, TODO tile
// vira 502 -- e logo depois 500, com o pool de render ainda indefinido.
//
// Aqui a falha fica contida na requisicao que a causou, e passa a deixar
// rastro no log (antes so dava para contar pelos reinicios).
process.on('uncaughtException', (e) => {
  console.error('[guard] uncaughtException contida:', (e && e.message) || e);
});
process.on('unhandledRejection', (e) => {
  console.error('[guard] unhandledRejection contida:', (e && e.message) || e);
});
console.error('[guard] ativo: erros nao tratados nao derrubam mais o processo');
