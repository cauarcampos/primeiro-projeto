
class Program
{
    static void Main()
        
    {
        Console.WriteLine("=== Esse programa imprime numeros pares de 0 a 100 ===");
        Console.WriteLine("Precione qualquer tecla para continuar:");
        Console.ReadKey();
        int num = 0;

        while (num <= 100)
        {
            Console.WriteLine(num);
            num += 2;
        }

        Console.WriteLine("FIM, Precione qualquer tecla para sair ;)");
        Console.ReadKey();
    }
}