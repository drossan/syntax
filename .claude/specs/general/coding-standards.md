# Coding standards (generales)

> Spec **user-owned**: `/task-init` la materializa con la regla base de abajo; a partir de ahí es **tuya**
> para extender. A diferencia de `honesty-rules.md`, `bootstrap.sh` **no** la restaura ni `doctor` la
> vigila — igual que las otras specs generales que el `HOW-TO-START-A-TASK.md` referencia (`testing.md`,
> `error-handling.md`, `security.md`, `git-workflow.md`), punteros que rellenas tú. El HOW-TO la enlaza
> como spec transversal de "cualquier código".

## No-duplicación

- **No dupliques código bajo ningún concepto** salvo **aprobación explícita del usuario**. Si vas a
  copiar/pegar lógica que ya existe, deténte: extrae a una función/módulo, reutiliza lo existente o
  pregunta. La duplicación es deuda desde el primer commit.

<!-- Extiende con los coding-standards de tu repo: naming, límites de complejidad/tamaño, estilo,
     inmutabilidad, manejo de nulos, etc. Son criterios transversales a cualquier código del repo. -->
