/**
 * Inicializa los selects de países en los contenedores especificados.
 * @param {string|null} tabId - ID del contenedor (pestaña) a inicializar, o null para todos.
 */
function initSelects(tabId = null) {
    const containers = tabId ? [document.getElementById(tabId)] : [
        document.getElementById('datos-personales'),
        document.getElementById('datos-compania'),
        document.getElementById('datos-usuario'),
        document.getElementById('add-branch-form')
    ];

    containers.forEach(container => {
        if (!container) return;

        const paisesSelect = container.querySelector('select[name="paises"]');

        if (paisesSelect) {
            fetch("/get-paises", { method: "GET" })
                .then(response => {
                    if (!response.ok) {
                        throw new Error("Error al cargar países: " + response.status);
                    }
                    return response.json();
                })
                .then(data => {
    
                    paisesSelect.innerHTML = '<option value="" selected>Selecciona el país</option>';

                    if (data && data.length > 0) {
                        data.forEach(pais => {
                            let option = document.createElement("option");
                            option.value = pais.id;
                            option.textContent = pais.nombre;
                            paisesSelect.appendChild(option);
                        });
                    } else {
                        console.warn("No se encontraron países");
                    }
                })
                .catch(error => {
                    console.error("Error al cargar países:", error);
                });
        }

        resetDependentSelects(container, 0);
    });
}

/**
 * Resetea los selects dependientes (estados, municipios, colonias) en un contenedor.
 * @param {HTMLElement} container - Contenedor donde están los selects.
 * @param {number} level - Nivel de reseteo (0: todos, 1: desde estados, 2: desde municipios, 3: solo colonias).
 */
function resetDependentSelects(container, level = 0) {
    if (!container) return;

    if (level <= 1) {
        const selectsEst = container.querySelector('select[name="estados"]');
        if (selectsEst) {
            selectsEst.innerHTML = '<option value="" selected>Selecciona el estado</option>';
            selectsEst.disabled = false;
        }
    }

    if (level <= 2) {
        const selectsMun = container.querySelector('select[name="municipios"]');
        if (selectsMun) {
            selectsMun.innerHTML = '<option value="" selected>Selecciona el municipio</option>';
            selectsMun.disabled = false;
        }
    }

    if (level <= 3) {
        const selectsCol = container.querySelector('select[name="idcolonia"]');
        if (selectsCol) {
            selectsCol.innerHTML = '<option value="" selected>Selecciona la colonia</option>';
            selectsCol.disabled = false;
        }
    }
}

/**
 * Carga estados según el país seleccionado.
 * @param {Event} event - Evento de cambio en el select de países.
 */
function selectPais(event) {
    const selectElement = event.target;
    const pais_id = selectElement.value;
    const container = findParentTab(selectElement);

    if (!container) {
        console.error("No se pudo encontrar el contenedor padre");
        return;
    }

    resetDependentSelects(container, 1);

    if (!pais_id) {
        console.warn("No se seleccionó ningún país");
        return;
    }

    fetch("/get-estados/" + pais_id, { method: "GET" })
        .then(response => {
            if (!response.ok) {
                throw new Error("Error al cargar estados: " + response.status);
            }
            return response.json();
        })
        .then(data => {

            const selectEst = container.querySelector('select[name="estados"]');
            if (!selectEst) {
                console.error("No se encontró el select de estados en este contenedor");
                return;
            }

            selectEst.innerHTML = '<option value="" selected>Selecciona el estado</option>';

            if (data && data.length > 0) {
                data.forEach(estado => {
                    let option = document.createElement("option");
                    option.value = estado.id;
                    option.textContent = estado.nombre;
                    selectEst.appendChild(option);
                });
                selectEst.hidden = false;
            } else {
                console.warn("No se encontraron estados para el país seleccionado");
            }
        })
        .catch(error => {
            console.error("Error al cargar estados:", error);
        });
}

/**
 * Carga municipios según el estado seleccionado.
 * @param {Event} event - Evento de cambio en el select de estados.
 */
function selectEstado(event) {
    const estado_id = event.target.value;
    // Busca el formulario/contenedor más cercano
    const container = event.target.closest('form') || document;
    // Busca el select de municipio dentro de ese contenedor
    let selectMun = container.querySelector('select[name="municipios"], #edit_municipio, #owner_municipios, #comp_municipios');
    let selectCol = container.querySelector('select[name="idcolonia"], #edit_colonia, #owner_idcolonia, #comp_idcolonia');
    

    if (selectMun) {
        selectMun.innerHTML = '<option value="" disabled selected>Selecciona el municipio</option>';
    }
    if (selectCol) {
        selectCol.innerHTML = '<option value="" disabled selected>Selecciona la colonia</option>';
    }

    if (!estado_id) return;

    fetch("/get-municipios/" + estado_id, { method: "GET" })
        .then(response => response.json())
        .then(data => {
            if (selectMun) {
                data.forEach(mun => {
                    let option = document.createElement("option");
                    option.value = mun.id;
                    option.textContent = mun.nombre;
                    selectMun.appendChild(option);
                });
                selectMun.hidden = false;
            }
        });
}

/**
 * Carga colonias según el municipio seleccionado.
 * @param {Event} event - Evento de cambio en el select de municipios.
 */
function selectMunicipio(event) {
    const municipio_id = event.target.value;
    // Busca el formulario/contenedor más cercano
    const container = event.target.closest('form') || document;
    // Busca el select de colonia dentro de ese contenedor
    let selectCol = container.querySelector('select[name="idcolonia"], #edit_colonia, #owner_idcolonia, #comp_idcolonia');
    if (selectCol) {
        selectCol.innerHTML = '<option value="" disabled selected>Selecciona la colonia</option>';
    }
    if (!municipio_id) return;
    fetch("/get-colonias/" + municipio_id)
        .then(r => r.json())
        .then(data => {
            //console.log("Colonias que llegan:", data);
            if (selectCol) {
                data.forEach(col => {
                    let option = document.createElement("option");
                    option.value = col.id;
                    option.textContent = col.nombre;
                    selectCol.appendChild(option);
                });
            }
        });
}

/**
 * Encuentra el contenedor padre (tab-pane) de un elemento.
 * @param {HTMLElement} element - Elemento del cual buscar el contenedor.
 * @returns {HTMLElement|null} - Contenedor padre o null si no se encuentra.
 */
function findParentTab(element) {
    let current = element;
    while (current && !(current.classList.contains('tab-pane') || current.tagName === 'FORM')) {
        current = current.parentElement;
    }
    return current;
}


/**
 * Llena los selects de dirección (país, estado, municipio, colonia) y campos de calle/número.
 * @param {Object} opts - Opciones para la función.
 * @param {string} opts.rfc - RFC del usuario a consultar.
 * @param {string} opts.paisId - ID del select de país.
 * @param {string} opts.estadoId - ID del select de estado.
 * @param {string} opts.municipioId - ID del select de municipio.
 * @param {string} opts.coloniaId - ID del select de colonia.
 * @param {string} opts.calleId - ID del input de calle.
 * @param {string} opts.numeroId - ID del input de número.
 */
async function loadAddressFields({ rfc, paisId, estadoId, municipioId, coloniaId, calleId, numeroId }) {
    const paisSelect = document.getElementById(paisId);
    const estadoSelect = document.getElementById(estadoId);
    const municipioSelect = document.getElementById(municipioId);
    const coloniaSelect = document.getElementById(coloniaId);

    // Limpiar selects
    paisSelect.innerHTML = '<option value="" disabled selected>Selecciona el país</option>';
    estadoSelect.innerHTML = '<option value="" disabled selected>Selecciona el estado</option>';
    municipioSelect.innerHTML = '<option value="" disabled selected>Selecciona el municipio</option>';
    coloniaSelect.innerHTML = '<option value="" disabled selected>Selecciona la colonia</option>';

    try {
        const resp = await fetch(`/get_dueño/${rfc}`);
        if (!resp.ok) throw new Error('No se pudo obtener datos de dirección');
        const data = await resp.json();

        // Países
        const paisesResp = await fetch('/get-paises');
        const paises = await paisesResp.json();
        paises.forEach(pais => {
            let option = document.createElement('option');
            option.value = pais.id;
            option.textContent = pais.nombre;
            if (pais.id == data.idpais) option.selected = true;
            paisSelect.appendChild(option);
        });

        // Estados
        const estadosResp = await fetch(`/get-estados/${data.idpais}`);
        const estados = await estadosResp.json();
        estados.forEach(estado => {
            let option = document.createElement('option');
            option.value = estado.id;
            option.textContent = estado.nombre;
            if (estado.id == data.idestado) option.selected = true;
            estadoSelect.appendChild(option);
        });

        // Municipios
        const municipiosResp = await fetch(`/get-municipios/${data.idestado}`);
        const municipios = await municipiosResp.json();
        municipios.forEach(mun => {
            let option = document.createElement('option');
            option.value = mun.id;
            option.textContent = mun.nombre;
            if (mun.id == data.idmunicipio) option.selected = true;
            municipioSelect.appendChild(option);
        });

        // Colonias
        const coloniasResp = await fetch(`/get-colonias/${data.idmunicipio}`);
        const colonias = await coloniasResp.json();
        let coloniaEncontrada = false;
        colonias.forEach(col => {
            let option = document.createElement('option');
            option.value = col.id;
            option.textContent = col.nombre;
            if (col.id == data.idcolonia) {
                option.selected = true;
                coloniaEncontrada = true;
            }
            coloniaSelect.appendChild(option);
        });
        if (!coloniaEncontrada && data.idcolonia && data.colonia) {
            // Agrega la colonia manualmente si no está en el array
            let option = document.createElement('option');
            option.value = data.idcolonia;
            option.textContent = data.colonia + ' (No encontrada en municipio)';
            option.selected = true;
            coloniaSelect.appendChild(option);
        }

        // Calle y número
        document.getElementById(calleId).value = data.calle || '';
        document.getElementById(numeroId).value = data.numero || '';

    } catch (error) {
        console.error('Error al cargar dirección:', error);
    }
}