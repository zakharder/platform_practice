const resultsNode = document.getElementById("results");
const resultsMetaNode = document.getElementById("results-meta");
const searchForm = document.getElementById("search-form");
const uploadForm = document.getElementById("upload-form");
const uploadStatusNode = document.getElementById("upload-status");
const uploadButton = uploadForm.querySelector('button[type="submit"]');

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMaterials(materials) {
  if (!materials.length) {
    resultsNode.innerHTML = `
      <article class="material-card">
        <h4>Материалы не найдены</h4>
        <p>Попробуйте изменить поисковый запрос или загрузите новый файл через форму справа.</p>
      </article>
    `;
    return;
  }

  resultsNode.innerHTML = materials
    .map((material) => {
      const tags = material.tags.length
        ? material.tags.map((tag) => `<span class="chip">${escapeHtml(tag)}</span>`).join("")
        : '<span class="chip">Без тегов</span>';

      return `
        <article class="material-card">
          <div class="material-card__top">
            <div>
              <h4>${escapeHtml(material.title)}</h4>
              <p>${escapeHtml(material.description || "Описание не добавлено.")}</p>
            </div>
            <span class="chip">${escapeHtml(material.extension)}</span>
          </div>
          <div class="material-card__meta">${tags}</div>
          <a class="download-link" href="${material.download_url}">Скачать файл</a>
        </article>
      `;
    })
    .join("");
}

async function loadMaterials(query = "") {
  resultsMetaNode.textContent = "Загрузка материалов...";
  const url = query ? `/api/materials?q=${encodeURIComponent(query)}` : "/api/materials";
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("Не удалось получить список материалов.");
  }

  const materials = await response.json();
  resultsMetaNode.textContent = `Найдено материалов: ${materials.length}`;
  renderMaterials(materials);
}

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = new FormData(searchForm).get("q").toString().trim();
  await loadMaterials(query);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadStatusNode.textContent = "Файл загружается...";
  uploadButton.disabled = true;

  try {
    const formData = new FormData(uploadForm);
    const response = await fetch("/api/materials", {
      method: "POST",
      body: formData,
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() };

    if (!response.ok) {
      uploadStatusNode.textContent = payload.error || "Не удалось загрузить файл.";
      return;
    }

    uploadStatusNode.textContent = "Материал успешно загружен.";
    uploadForm.reset();
    await loadMaterials(searchForm.querySelector("input").value.trim());
  } catch (_error) {
    uploadStatusNode.textContent = "Ошибка соединения при загрузке файла. Проверьте сервер и попробуйте снова.";
  } finally {
    uploadButton.disabled = false;
  }
});

loadMaterials().catch(() => {
  resultsMetaNode.textContent = "Не удалось загрузить список материалов.";
  resultsNode.innerHTML = `
    <article class="material-card">
      <h4>Ошибка подключения</h4>
      <p>Проверьте, что сервер запущен и доступен пользователям.</p>
    </article>
  `;
});
