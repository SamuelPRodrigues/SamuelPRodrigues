# Mapa de Calor Rodovias x Clima Brasil

Site estático para visualizar risco climático e potencial de congestionamento em corredores rodoviários brasileiros.

A aplicação usa dados meteorológicos reais da Open-Meteo diretamente no navegador. Para trânsito em tempo real, há integração opcional com TomTom Traffic API mediante chave do usuário. Também há importação local de CSV da PRF para gerar heatmap com ocorrências reais de acidentes em rodovias federais.

## Publicação

Este repositório contém um workflow em `.github/workflows/pages.yml` para publicar o `index.html` no GitHub Pages usando GitHub Actions.

Quando o Pages estiver ativo, o endereço esperado é:

https://samuelprodriques.github.io/SamuelPRodrigues/

Se aparecer 404, ative em: Settings > Pages > Build and deployment > Source: GitHub Actions.
